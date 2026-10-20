"""007 离线测试：MCP Server 六工具（fastmcp 进程内客户端，零网络零外部进程）。

覆盖：US1 全链（调研→组世界→跑仿真→导出）/ US2 错误语义 / US3 web 工具 /
SC-004 import 边界 grep。
"""
import asyncio
import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import orchestrator.mcp_server as mcp_mod
from orchestrator.mcp_server import build_server
from orchestrator.store import Store

CHAR = {
    "asset_id": "char_a", "type": "character", "name": "甲",
    "appearance": {"visual_prompt": "look"},
    "persona_spec": {"age": 30, "occupation": "旅人", "personality": "沉稳",
                     "beliefs": "各扫门前雪", "speech_style": "简短",
                     "secret": "甲的秘密"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}
SCENE = {
    "asset_id": "scene_x", "type": "scene", "name": "酒楼",
    "appearance": {"visual_prompt": "tavern", "description": "临河酒楼"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}

EXPECTED_TOOLS = {"research_asset", "create_world", "run_simulation",
                  "export_events", "web_search", "web_fetch"}


@pytest.fixture()
def mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATIVE_DB", str(tmp_path / "mcp.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    store = Store(str(tmp_path / "mcp.db"))
    from db.init_db import init as init_db
    init_db(str(tmp_path / "mcp.db"))
    store = Store(str(tmp_path / "mcp.db"))
    store.put_asset(CHAR)
    store.put_asset(SCENE)
    store.close()
    return build_server()


def call(mcp, name, args):
    async def _go():
        async with Client(mcp) as c:
            return await c.call_tool(name, args)
    return asyncio.run(_go())


def list_tools(mcp):
    async def _go():
        async with Client(mcp) as c:
            return await c.list_tools()
    return asyncio.run(_go())


# ---------- US1：工具发现与全链 ----------

def test_list_tools_six_with_schema(mcp):
    tools = list_tools(mcp)
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS
    for t in tools:
        assert t.inputSchema, f"{t.name} 缺参数 schema"


def test_full_chain(mcp, tmp_path, monkeypatch):
    # 调研工具（mock 掉外部调研，走真实入库）
    def fake_research(query, asset_type, store):
        asset = dict(CHAR if asset_type == "character" else SCENE,
                     asset_id=f"{asset_type}_new1")
        return store.put_asset(asset)
    monkeypatch.setattr(mcp_mod, "_research_asset", fake_research)

    r1 = call(mcp, "research_asset", {"query": "某酒楼", "asset_type": "scene"})
    assert r1.data["asset_id"] == "scene_new1"
    assert r1.data["deduplicated"] is False

    r2 = call(mcp, "create_world", {
        "world_id": "w1", "character_ids": ["char_a"],
        "location_id": "scene_x"})
    assert r2.data["world_id"] == "w1"
    assert r2.data["action_count"] == 3

    r3 = call(mcp, "run_simulation", {
        "world_id": "w1", "run_id": "run1", "ticks": 2, "backend": "mock"})
    assert r3.data["event_count"] == 3  # 1 开场 + 2 tick × 1 角色
    assert r3.data["cost_tokens"] is None

    out = tmp_path / "out.jsonl"
    r4 = call(mcp, "export_events", {"run_id": "run1", "out_path": str(out)})
    assert r4.data["count"] == 3
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    assert json.loads(lines[0])["type"] == "scene_change"


# ---------- US2：错误语义 ----------

def test_blank_query_rejected(mcp):
    with pytest.raises(ToolError, match="查询词"):
        call(mcp, "research_asset", {"query": "  ", "asset_type": "scene"})


def test_invalid_asset_type_rejected(mcp):
    with pytest.raises(ToolError, match="不支持的资产类型"):
        call(mcp, "research_asset", {"query": "q", "asset_type": "weapon"})


def test_run_simulation_world_not_found(mcp):
    with pytest.raises(ToolError, match="WorldNotFound"):
        call(mcp, "run_simulation", {"world_id": "ghost", "run_id": "r",
                                     "ticks": 1, "backend": "mock"})


def test_resume_without_snapshot(mcp):
    call(mcp, "create_world", {"world_id": "w1", "character_ids": ["char_a"],
                               "location_id": "scene_x"})
    with pytest.raises(ToolError, match="无可续跑快照"):
        call(mcp, "run_simulation", {"world_id": "w1", "run_id": "r",
                                     "ticks": 1, "backend": "mock",
                                     "resume": True})


def test_research_service_failure_readable(mcp, monkeypatch):
    def boom(query, asset_type, store):
        raise ConnectionError("unreachable")
    monkeypatch.setattr(mcp_mod, "_research_asset", boom)
    with pytest.raises(ToolError, match="ConnectionError"):
        call(mcp, "research_asset", {"query": "q", "asset_type": "scene"})


def test_create_world_duplicate_rejected_then_reset(mcp):
    args = {"world_id": "w1", "character_ids": ["char_a"],
            "location_id": "scene_x"}
    call(mcp, "create_world", args)
    with pytest.raises(ToolError, match="WorldExists"):
        call(mcp, "create_world", args)
    ok = call(mcp, "create_world", dict(args, reset=True))
    assert ok.data["world_id"] == "w1"


def test_server_survives_errors(mcp):
    """错误之后 server 仍可正常服务（进程内等价验证）。"""
    with pytest.raises(ToolError):
        call(mcp, "research_asset", {"query": "  ", "asset_type": "scene"})
    ok = call(mcp, "create_world", {"world_id": "w1",
                                    "character_ids": ["char_a"],
                                    "location_id": "scene_x"})
    assert ok.data["world_id"] == "w1"


# ---------- US3：web 工具 ----------

def test_web_search_returns_structured(mcp, monkeypatch):
    monkeypatch.setattr(mcp_mod, "_web_search", lambda q, count=8: [
        {"title": "甲", "url": "https://a.example", "summary": "摘要甲",
         "snippet": "片段"}])
    r = call(mcp, "web_search", {"query": "q", "count": 3})
    assert r.data["results"] == [{"title": "甲", "url": "https://a.example",
                                  "summary": "摘要甲"}]


def test_web_search_empty(mcp, monkeypatch):
    monkeypatch.setattr(mcp_mod, "_web_search", lambda q, count=8: [])
    r = call(mcp, "web_search", {"query": "q"})
    assert r.data["results"] == []


def test_web_fetch_success_and_failure(mcp, monkeypatch):
    monkeypatch.setattr(mcp_mod, "_web_fetch",
                        lambda u: {"title": "T", "content": "正文"})
    r = call(mcp, "web_fetch", {"url": "https://a.example"})
    assert r.data == {"title": "T", "content": "正文"}
    monkeypatch.setattr(mcp_mod, "_web_fetch", lambda u: None)
    with pytest.raises(ToolError, match="FetchFailed"):
        call(mcp, "web_fetch", {"url": "https://dead.example"})


# ---------- SC-004：import 边界 ----------

def test_mcp_server_import_boundary():
    import ast
    from pathlib import Path

    path = Path(mcp_mod.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    allowed_prefixes = ("orchestrator.", "db.", "gptr_deepseek_retriever",
                        "fastmcp")
    stdlib_ok = {"json", "os"}
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # 相对导入 = orchestrator 内部，允许
            mods = [node.module or ""]
        else:
            continue
        for mod in mods:
            root = mod.split(".")[0]
            if mod in stdlib_ok or root in stdlib_ok:
                continue
            if mod.startswith(allowed_prefixes) or root == "orchestrator":
                continue
            offenders.append(mod)
    assert offenders == [], f"mcp_server.py 越界 import: {offenders}"
