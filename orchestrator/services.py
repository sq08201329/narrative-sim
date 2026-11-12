"""本地技术栈服务管理；运行状态只由本模块读写。"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import psutil

from .runtime import is_frozen, resource_root

ROOT = resource_root()


class ServiceError(RuntimeError):
    pass


@dataclass
class ServiceSpec:
    name: str
    command: list[str]
    cwd: Path
    port: int
    health_url: str
    marker: str
    host: str = "localhost"
    ready_timeout: float = 40
    env: dict[str, str] = field(default_factory=dict)


def _http_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


class StackManager:
    def __init__(self, home: Path, db: Path, specs: list[ServiceSpec]):
        self.home = Path(home)
        self.db = Path(db)
        self.specs = specs
        self.run_dir = self.home / "run"
        self.log_dir = self.home / "logs"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _record_path(self, spec: ServiceSpec) -> Path:
        return self.run_dir / f"{spec.name}.json"

    def _read_record(self, spec: ServiceSpec) -> dict | None:
        try:
            record = json.loads(self._record_path(spec).read_text(encoding="utf-8"))
            return record if record.get("name") == spec.name else None
        except (OSError, ValueError, TypeError):
            return None

    def _write_record(self, spec: ServiceSpec, pid: int, created: float,
                      command: list[str]) -> None:
        path = self._record_path(spec)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({
            "name": spec.name, "pid": pid, "created": created, "command": command,
            "log": str(self.log_dir / f"{spec.name}.err.log"),
        }, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)

    def _owned_process(self, spec: ServiceSpec) -> psutil.Process | None:
        record = self._read_record(spec)
        if not record:
            return None
        try:
            process = psutil.Process(int(record["pid"]))
            if not process.is_running() or abs(process.create_time() - float(record["created"])) > 0.01:
                return None
            if spec.marker not in " ".join(process.cmdline()):
                return None
            return process
        except (psutil.Error, KeyError, ValueError, TypeError, OSError):
            return None

    def _listener_pid(self, spec: ServiceSpec) -> int | None:
        try:
            for connection in psutil.net_connections(kind="tcp"):
                if (connection.laddr and connection.laddr.port == spec.port
                        and connection.status == psutil.CONN_LISTEN):
                    return connection.pid
        except psutil.AccessDenied:
            for process in psutil.process_iter():
                try:
                    for connection in process.net_connections(kind="tcp"):
                        if (connection.laddr and connection.laddr.port == spec.port
                                and connection.status == psutil.CONN_LISTEN):
                            return process.pid
                except (psutil.Error, OSError):
                    continue
        except (psutil.Error, OSError):
            pass
        return None

    def _port_open(self, spec: ServiceSpec) -> bool:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((spec.host, spec.port)) == 0

    def _healthy(self, spec: ServiceSpec) -> bool:
        return _http_ready(spec.health_url) if spec.health_url else self._port_open(spec)

    def _status_one(self, spec: ServiceSpec) -> dict:
        process = self._owned_process(spec)
        healthy = self._healthy(spec)
        listener = (self._listener_pid(spec)
                    if process or healthy or self._port_open(spec) else None)
        if healthy:
            state = "ready" if process else "external"
        elif process or listener:
            state = "unhealthy"
        else:
            state = "stopped"
        return {
            "name": spec.name, "state": state,
            "pid": process.pid if process else listener,
            "managed": process is not None, "port": spec.port,
            "log": str(self.log_dir / f"{spec.name}.err.log"),
        }

    def status(self) -> list[dict]:
        return [self._status_one(spec) for spec in self.specs]

    def _spawn(self, spec: ServiceSpec) -> None:
        out_path = self.log_dir / f"{spec.name}.out.log"
        err_path = self.log_dir / f"{spec.name}.err.log"
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", **spec.env)
        flags = 0
        if os.name == "nt":
            flags = (subprocess.CREATE_NEW_PROCESS_GROUP
                     | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
        try:
            with open(out_path, "ab") as out, open(err_path, "ab") as err:
                process = subprocess.Popen(
                    spec.command, cwd=spec.cwd, env=env,
                    stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                    creationflags=flags, close_fds=True)
            created = psutil.Process(process.pid).create_time()
            self._write_record(spec, process.pid, created, spec.command)
        except Exception as exc:
            raise ServiceError(f"{spec.name} 启动失败: {exc}；日志 {err_path}") from exc

        deadline = time.monotonic() + spec.ready_timeout
        while time.monotonic() < deadline:
            if self._healthy(spec):
                return
            if process.poll() is not None:
                break
            time.sleep(0.1)
        self._stop_one(spec)
        raise ServiceError(
            f"{spec.name} 在 {spec.ready_timeout:g}s 内未就绪；日志 {err_path}")

    def _start_one(self, spec: ServiceSpec) -> dict:
        current = self._status_one(spec)
        if current["state"] in {"ready", "external"}:
            return current
        if current["state"] == "unhealthy":
            raise ServiceError(
                f"{spec.name} 端口 {spec.port} 被占用或已有进程未就绪；"
                f"请先 restart 或检查 {current['log']}")
        self._record_path(spec).unlink(missing_ok=True)
        self._spawn(spec)
        return self._status_one(spec)

    def start(self) -> list[dict]:
        return [self._start_one(spec) for spec in self.specs]

    def _stop_one(self, spec: ServiceSpec) -> dict:
        process = self._owned_process(spec)
        if process:
            try:
                process.terminate()
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            except psutil.NoSuchProcess:
                pass
        self._record_path(spec).unlink(missing_ok=True)
        return self._status_one(spec)

    def stop(self) -> list[dict]:
        return [self._stop_one(spec) for spec in reversed(self.specs)]

    def restart(self) -> list[dict]:
        self.stop()
        return self.start()


def _service_address(variable: str, health_path: str) -> tuple[str, int, str]:
    raw = os.environ.get(variable, "").strip()
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.hostname:
        raise ServiceError(f"{variable} 必须配置完整服务地址，当前未设置")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    origin = f"{parsed.scheme}://{parsed.hostname}:{port}"
    return parsed.hostname, port, origin + health_path


def _model_file() -> Path:
    return Path(os.environ.get("EMBEDDING_MODEL_FILE") or
                ROOT / "models" / "model.litertlm").resolve()


def _default_specs(home: Path, db: Path) -> list[ServiceSpec]:
    embed_host, embed_port, embed_health = _service_address(
        "EMBEDDING_API_BASE", "/v1/models")
    gptr_host, gptr_port, gptr_health = _service_address("GPTR_MCP_URL", "/health")
    narrative_host = os.environ.get("MCP_HOST", "localhost")
    narrative_port = int(os.environ.get("MCP_PORT", "8300"))
    litert = os.environ.get("LITERT_LM") or shutil.which("litert-lm") or "litert-lm"
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    gptr_env = {
        "MCP_TRANSPORT": "streamable-http", "RETRIEVER": "deepseek",
        "FAST_LLM": "deepseek:deepseek-flash", "SMART_LLM": "deepseek:deepseek-flash",
        "STRATEGIC_LLM": "deepseek:deepseek-flash", "DEEPSEEK_API_KEY": key,
        "OPENAI_API_KEY": key, "SMART_TOKEN_LIMIT": "8000",
        "STRATEGIC_TOKEN_LIMIT": "8000",
    }
    frozen = is_frozen()
    gptr_command = ([sys.executable, "_gptr"] if frozen else
                    [sys.executable, str(ROOT / "packages" / "gptr-mcp" / "server.py")])
    narrative_command = [sys.executable]
    if not frozen:
        narrative_command += ["-m", "orchestrator.cli"]
    narrative_command += ["--home", str(home), "--db", str(db), "mcp",
                          "--host", narrative_host, "--port", str(narrative_port)]
    return [
        ServiceSpec("embedding", [litert, "serve", "--host", embed_host,
                                  "--port", str(embed_port)], _model_file().parent,
                    embed_port, embed_health, "litert-lm", host=embed_host),
        ServiceSpec("gptr-mcp", gptr_command, ROOT, gptr_port,
                    gptr_health, "_gptr" if frozen else "server.py",
                    host=gptr_host, env=gptr_env),
        ServiceSpec("narrative-sim", narrative_command, ROOT, narrative_port, "",
                    "mcp" if frozen else "orchestrator.cli", host=narrative_host,
                    env={"NARRATIVE_HOME": str(home), "NARRATIVE_DB": str(db),
                         "LIBRARY_DB": os.environ.get("LIBRARY_DB", "")}),
    ]


def _prepare_embedding() -> None:
    _, _, health = _service_address("EMBEDDING_API_BASE", "/v1/models")
    if _http_ready(health):
        return
    litert = os.environ.get("LITERT_LM") or shutil.which("litert-lm") or "litert-lm"
    model = os.environ.get("EMBEDDING_MODEL", "eg2-text-270m.litertlm")
    try:
        listed = subprocess.run([litert, "list"], capture_output=True, text=True)
    except OSError as exc:
        raise ServiceError(f"无法执行嵌入运行时，请检查 LITERT_LM: {exc}") from exc
    if listed.returncode != 0:
        raise ServiceError(f"无法查询嵌入模型，请检查 LITERT_LM: {listed.stderr.strip()}")
    if model not in listed.stdout:
        model_file = _model_file()
        if not model_file.is_file():
            raise ServiceError(f"嵌入模型文件不存在: {model_file}；请配置 EMBEDDING_MODEL_FILE")
        imported = subprocess.run([litert, "import", str(model_file), model],
                                  capture_output=True, text=True)
        if imported.returncode != 0:
            raise ServiceError(f"嵌入模型导入失败: {imported.stderr.strip()}")


def service_action(action: str, home: Path, db: Path) -> dict:
    if action in {"start", "restart"}:
        _prepare_embedding()
    manager = StackManager(home, db, _default_specs(home, db))
    statuses = getattr(manager, action)()
    return {"action": action, "database": str(db),
            "ready": all(item["state"] in {"ready", "external"} for item in statuses),
            "services": statuses}
