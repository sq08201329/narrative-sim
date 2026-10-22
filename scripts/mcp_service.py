"""MCP server 服务管理：start / stop / restart / status。

用法（项目根目录）：
    uv run python scripts/mcp_service.py start     # 后台启动（日志 logs/mcp_server.log）
    uv run python scripts/mcp_service.py status    # 查进程 + 端口 + 工具数
    uv run python scripts/mcp_service.py stop
    uv run python scripts/mcp_service.py restart

环境变量沿用 run_mcp_server.py 口径：NARRATIVE_DB / MCP_TRANSPORT /
MCP_HOST / MCP_PORT 在 start 时继承当前环境。
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "mcp_server.log"
PID_FILE = LOG_DIR / "mcp_server.pid"

HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8300"))


def _pid_alive(pid: int) -> bool:
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                       capture_output=True)  # GBK 输出，按字节匹配
    return str(pid).encode() in (r.stdout or b"")


def _port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex((HOST, PORT)) == 0


def _read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def start() -> int:
    pid = _read_pid()
    if pid and _pid_alive(pid) and _port_open():
        print(f"已在运行：pid {pid}，http://{HOST}:{PORT}/mcp")
        return 0
    if _port_open():
        print(f"端口 {PORT} 被非受管进程占用（pid 不在记录中）。"
              f"先 taskkill 或换 MCP_PORT。", file=sys.stderr)
        return 2
    LOG_DIR.mkdir(exist_ok=True)
    err_log = LOG_DIR / "mcp_server.err.log"
    PID_FILE.unlink(missing_ok=True)  # 防读旧 pid（服务器启动时自写新 pid）
    # PowerShell Start-Process：真正独立进程 + 隐藏窗口；**不等其退出**
    # （Start-Process 的重定向会让 powershell 驻留，故 Popen 即发即弃）
    ps = (
        f"Start-Process -WindowStyle Hidden "
        f"-FilePath '{sys.executable}' "
        f"-ArgumentList 'scripts/run_mcp_server.py' "
        f"-WorkingDirectory '{ROOT}' "
        f"-RedirectStandardOutput '{LOG_FILE}' "
        f"-RedirectStandardError '{err_log}'"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", ps],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        cwd=ROOT,
    )
    for _ in range(24):
        if _port_open() and _read_pid():
            print(f"已启动：pid {_read_pid()}，http://{HOST}:{PORT}/mcp")
            print(f"日志：{LOG_FILE}")
            return 0
        time.sleep(0.5)
    print("端口 12s 内未就绪，请查日志", file=sys.stderr)
    return 1


def stop() -> int:
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        print("未在运行")
        return 0
    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                   capture_output=True)
    PID_FILE.unlink(missing_ok=True)
    print(f"已停止：pid {pid}")
    return 0


def status() -> int:
    pid = _read_pid()
    alive = bool(pid and _pid_alive(pid))
    port = _port_open()
    print(f"进程：{'存活 pid ' + str(pid) if alive else '无受管进程（或 pid 漂移）'}")
    print(f"端口：{HOST}:{PORT} {'监听中' if port else '未监听'}")
    print(f"日志：{LOG_FILE}")
    if port:
        try:
            import asyncio
            from fastmcp import Client

            async def probe():
                async with Client(f"http://{HOST}:{PORT}/mcp") as c:
                    return len(await c.list_tools())

            print(f"工具数：{asyncio.run(probe())}")
        except Exception as e:
            print(f"工具探测失败：{e}")
    return 0 if port else 1


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        return start()
    if cmd == "stop":
        return stop()
    if cmd == "restart":
        stop()
        return start()
    if cmd == "status":
        return status()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
