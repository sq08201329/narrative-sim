import asyncio
import json
import os
import subprocess
import time
import socket
import urllib.request
import zipfile
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from db.init_db import init as init_db
from orchestrator.store import Store
from scripts.run_minimal_chain import CHARACTER, SCENE

ROOT = Path(__file__).resolve().parent.parent.parent
APP = ROOT / "dist" / "NarrativeSim"
EXE = APP / "NarrativeSim.exe"
pytestmark = pytest.mark.skipif(not EXE.exists(), reason="先构建独立应用")


def env_for(home):
    env = dict(os.environ, NARRATIVE_HOME=str(home), PYTHONUTF8="1")
    env.pop("NARRATIVE_DB", None)
    env.pop("LIBRARY_DB", None)
    return env


def seed(db):
    init_db(str(db))
    store = Store(str(db))
    store.put_asset(CHARACTER)
    store.put_asset(SCENE)
    store.close()


def test_frozen_offline_workflow_from_other_cwd(tmp_path):
    home = tmp_path / "用户 数据"
    db = home / "data/projects/test.db"
    seed(db)
    cwd = tmp_path / "任意 cwd"
    cwd.mkdir()
    base = [str(EXE), "--home", str(home), "--db", str(db)]
    created = subprocess.run([*base, "world", "create", "w_frozen", "--characters",
                              CHARACTER["asset_id"], "--location", SCENE["asset_id"]],
                             cwd=cwd, env=env_for(home), capture_output=True, text=True, encoding="utf-8")
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["world_id"] == "w_frozen"
    run = subprocess.run([*base, "run", "w_frozen", "--run-id", "r_frozen",
                          "--ticks", "4", "--backend", "mock"],
                         cwd=cwd, env=env_for(home), capture_output=True, text=True, encoding="utf-8")
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["event_count"] == 5
    out = home / "exports/events.jsonl"
    exported = subprocess.run([*base, "export", "r_frozen", "--out", str(out)],
                              cwd=cwd, env=env_for(home), capture_output=True, text=True, encoding="utf-8")
    assert exported.returncode == 0, exported.stderr
    assert len(out.read_text(encoding="utf-8").splitlines()) == 5
    assert (home / "config.ini").is_file()
    assert not (cwd / "config.ini").exists()


def test_frozen_stdio_mcp_and_config_preserved(tmp_path):
    home = tmp_path / "home"
    db = home / "data/projects/mcp.db"
    seed(db)
    (home / "logs").mkdir(parents=True, exist_ok=True)
    transport = StdioTransport(
        command=str(EXE), args=["--home", str(home), "--db", str(db),
                                "mcp", "--transport", "stdio"], cwd=str(tmp_path))

    async def verify():
        async with Client(transport) as client:
            return await client.call_tool("list_assets", {})

    result = asyncio.run(verify())
    assert result.data["assets"][0]["asset_id"] == CHARACTER["asset_id"]
    config = home / "config.ini"
    original = config.read_bytes()
    help_result = subprocess.run([str(EXE), "--home", str(home), "--help"],
                                 env=env_for(home), capture_output=True)
    assert help_result.returncode == 0
    assert config.read_bytes() == original


def test_distribution_zip_and_hygiene():
    archive = ROOT / "dist" / "NarrativeSim-windows-x64.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as bundle:
        assert {Path(name).parts[0] for name in bundle.namelist()} == {"NarrativeSim"}
    forbidden = [path for path in APP.rglob("*")
                 if path.name == ".env" or path.suffix in {".db", ".litertlm"}]
    assert forbidden == []
    assert (APP / "BUILD-INFO.json").is_file()
    assert (APP / "_internal/schemas/event.schema.json").is_file()
    assert list((APP / "_internal").glob("gptr_deepseek_retriever-*.dist-info"))
    assert list((APP / "_internal").glob("gpt_researcher-*.dist-info"))


def test_frozen_default_home_is_local_app_data(tmp_path):
    local = tmp_path / "local"
    env = dict(os.environ, LOCALAPPDATA=str(local))
    env.pop("NARRATIVE_HOME", None)
    env.pop("NARRATIVE_DB", None)
    result = subprocess.run([str(EXE), "status"], cwd=tmp_path, env=env,
                            capture_output=True)
    assert result.returncode in (0, 1)
    assert (local / "NarrativeSim" / "config.ini").is_file()
    assert not (tmp_path / "config.ini").exists()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_frozen_http_mcp_managed_lifecycle(tmp_path):
    from orchestrator.services import ServiceSpec, StackManager

    port = free_port()
    spec = ServiceSpec(
        "narrative-frozen",
        [str(EXE), "--home", str(tmp_path), "mcp", "--port", str(port)],
        tmp_path, port, "", "mcp", host="localhost", ready_timeout=30)
    manager = StackManager(tmp_path, tmp_path / "play.db", [spec])
    started = manager.start()
    try:
        assert started[0]["state"] == "ready"
        assert started[0]["managed"] is True
    finally:
        assert manager.stop()[0]["state"] == "stopped"


def test_frozen_gptr_health_and_stop(tmp_path):
    process = subprocess.Popen(
        [str(EXE), "_gptr"], cwd=tmp_path,
        env=dict(os.environ, MCP_TRANSPORT="streamable-http", RETRIEVER="deepseek",
                 OPENAI_API_KEY="startup-only", DEEPSEEK_API_KEY="startup-only",
                 PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 40
        while True:
            try:
                with urllib.request.urlopen("http://localhost:8000/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_frozen_init_distributes_templates_without_overwrite(tmp_path):
    home = tmp_path / "中文 home"
    result = subprocess.run([str(EXE), "--home", str(home), "init"],
                            env=env_for(home), capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert all(item["status"] == "created" for item in payload["files"])
    skill = home / "skills/narrative-sim/SKILL.md"
    assert skill.read_bytes() == (ROOT / "resources/skills/narrative-sim/SKILL.md").read_bytes()
    assert (APP / ".env.example").is_file()
    assert (APP / "_internal/resources/skills/narrative-sim/SKILL.md").is_file()

    skill.write_text("custom", encoding="utf-8")
    (home / ".env").write_text("custom", encoding="utf-8")
    again = subprocess.run([str(EXE), "--home", str(home), "init"],
                           env=env_for(home), capture_output=True, text=True, encoding="utf-8")
    assert again.returncode == 0
    assert all(item["status"] == "existing" for item in json.loads(again.stdout)["files"])
    assert skill.read_text(encoding="utf-8") == "custom"
    assert (home / ".env").read_text(encoding="utf-8") == "custom"
