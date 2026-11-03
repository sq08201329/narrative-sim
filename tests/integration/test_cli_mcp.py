import asyncio
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from db.init_db import init as init_db
from orchestrator.store import Store
from tests.contract.test_mcp_server import CHAR

ROOT = Path(__file__).resolve().parent.parent.parent


def test_cli_mcp_stdio_uses_unified_database_and_clean_stdout(tmp_path):
    db = tmp_path / "stdio.db"
    init_db(str(db))
    store = Store(str(db))
    store.put_asset(CHAR)
    store.close()

    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "orchestrator.cli", "--home", str(tmp_path),
              "--db", str(db), "mcp", "--transport", "stdio"],
        cwd=str(ROOT),
    )

    async def verify():
        async with Client(transport) as client:
            tools = await client.list_tools()
            result = await client.call_tool("list_assets", {})
            return tools, result

    tools, result = asyncio.run(verify())
    assert "list_assets" in {tool.name for tool in tools}
    assert result.data["assets"][0]["asset_id"] == CHAR["asset_id"]
