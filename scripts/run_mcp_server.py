"""M5 MCP Server 启动入口。

用法：uv run python scripts/run_mcp_server.py
环境变量：MCP_TRANSPORT（默认 streamable-http）/ MCP_HOST（默认 127.0.0.1）/
MCP_PORT（默认 8300）/ NARRATIVE_DB（默认 narrative_sim.db）。
启动零外部检查：调研/嵌入服务不在线不影响启动，工具调用时按各自口径报错。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402


def main() -> None:
    load_dotenv()
    from orchestrator.mcp_server import build_server

    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8300"))

    mcp = build_server()
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        print(f"MCP server 启动: {transport} http://{host}:{port}/mcp")
        mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    main()
