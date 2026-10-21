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
                  "export_events", "web_search", "web_fetch",
                  # 011 US1 读接口
                  "list_assets", "get_asset", "get_materials",
                  "search_materials", "get_events", "get_world_state",
                  "list_dm_calls",
                  # 011 US2 修订
                  "revise_asset", "rollback_asset",
                  # 011 US3 移交
                  "export_handoff",
                  # 011 US4 重拍
                  "reshoot",
                  # 011 FR-014 立项
                  "research_brief",
                  # 012 幕间记忆
                  "generate_interlude_memory", "get_interlude_memory"}


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


# ---------- 011 US1：读接口 ----------

def _seed_run(db_path):
    """直接经 Store 种一个完成的 run + 事件 + dm_call（读接口的被测数据）。"""
    from db.init_db import init as init_db
    init_db(str(db_path))
    s = Store(str(db_path))
    s.create_run("run_seed", "w_seed")
    s.put_event({
        "event_id": "e0001", "run_id": "run_seed", "tick": 0, "seq": 0,
        "type": "scene_change", "characters": ["char_a"],
        "location": "scene_x", "content": "开场", "emotion": "",
        "cause_refs": [],
        "shot_hint": {"camera": "wide", "duration_s": 3.0},
        "created_at": "2026-10-21T00:00:00+00:00",
    })
    s.put_dm_call("run_seed", 1, "act", "char_a", "{}", "hint", "叙事",
                  "[]", 10, 5, 0.5, False)
    s.finish_run("run_seed", "done")
    s.put_world_config("w_seed", json.dumps(
        {"character_ids": ["char_a"], "location_id": "scene_x"}))
    s.put_world_state("w_seed", 3, json.dumps({"tick": 3, "entities": []}))
    s.put_material("char_a", "皇城司侦缉手段", "test", "原料正文")
    s.close()


def test_read_tools_full_path(mcp, tmp_path):
    _seed_run(tmp_path / "mcp.db")

    r = call(mcp, "list_assets", {})
    ids = {a["asset_id"] for a in r.data["assets"]}
    assert {"char_a", "scene_x"} <= ids
    char_entry = next(a for a in r.data["assets"] if a["asset_id"] == "char_a")
    assert char_entry["current_revision"] == 0

    r = call(mcp, "get_asset", {"asset_id": "char_a"})
    assert r.data["persona_spec"]["secret"] == "甲的秘密"
    assert r.data["current_revision"] == 0
    assert "secrecy" in r.data  # secret 密级标注（创作可见/仿真不可见）

    r = call(mcp, "get_materials", {"asset_id": "char_a"})
    assert r.data["materials"][0]["query"] == "皇城司侦缉手段"
    assert r.data["materials"][0]["context"] == "原料正文"

    r = call(mcp, "search_materials", {"keyword": "侦缉"})
    assert len(r.data["materials"]) == 1
    r = call(mcp, "search_materials", {"keyword": "侦缉".upper()})
    assert len(r.data["materials"]) == 1  # 大小写不敏感
    r = call(mcp, "search_materials", {"keyword": "不存在的词"})
    assert r.data["materials"] == []

    r = call(mcp, "get_events", {"run_id": "run_seed"})
    assert len(r.data["events"]) == 1
    assert r.data["events"][0]["type"] == "scene_change"

    r = call(mcp, "get_world_state", {"world_id": "w_seed"})
    assert r.data["tick"] == 3

    r = call(mcp, "list_dm_calls", {"run_id": "run_seed"})
    assert len(r.data["dm_calls"]) == 1
    assert r.data["dm_calls"][0]["tokens_in"] == 10


def test_read_tools_not_found(mcp):
    with pytest.raises(ToolError, match="AssetNotFound"):
        call(mcp, "get_asset", {"asset_id": "ghost"})
    with pytest.raises(ToolError, match="RunNotFound"):
        call(mcp, "get_events", {"run_id": "ghost"})
    with pytest.raises(ToolError, match="RunNotFound"):
        call(mcp, "list_dm_calls", {"run_id": "ghost"})
    with pytest.raises(ToolError, match="WorldNotFound"):
        call(mcp, "get_world_state", {"world_id": "ghost"})


def test_read_tools_empty_semantics(mcp):
    """无原料/无快照为空集而非报错。"""
    r = call(mcp, "get_materials", {"asset_id": "char_a"})
    assert r.data["materials"] == []
    call(mcp, "create_world", {"world_id": "w_empty",
                               "character_ids": ["char_a"],
                               "location_id": "scene_x"})
    r = call(mcp, "get_world_state", {"world_id": "w_empty"})
    assert r.data == {"tick": None, "state": None}


# ---------- 011 US2：修订与回滚 ----------

def test_revise_and_rollback_via_mcp(mcp):
    r = call(mcp, "revise_asset", {
        "asset_id": "char_a",
        "patch": {"persona_spec": {"personality": "急躁"}},
        "reason": "创作调整", "author": "writer-agent"})
    assert r.data["revision"] == 1
    assert r.data["impacted"] == []  # 无世界引用
    assert r.data["warning"] is None

    r = call(mcp, "get_asset", {"asset_id": "char_a"})
    assert r.data["persona_spec"]["personality"] == "急躁"
    assert r.data["current_revision"] == 1

    r = call(mcp, "rollback_asset", {"asset_id": "char_a", "to_revision": 0})
    assert r.data["current_revision"] == 0
    r = call(mcp, "get_asset", {"asset_id": "char_a"})
    assert r.data["persona_spec"]["personality"] == "沉稳"


def test_revise_errors_via_mcp(mcp):
    with pytest.raises(ToolError, match="AssetNotFound"):
        call(mcp, "revise_asset", {"asset_id": "ghost",
                                   "patch": {"name": "x"}, "reason": "x"})
    with pytest.raises(ToolError, match="BadPatch"):
        call(mcp, "revise_asset", {"asset_id": "char_a", "patch": {},
                                   "reason": "空"})
    with pytest.raises(ToolError, match="RevisionConflict"):
        call(mcp, "revise_asset", {"asset_id": "char_a",
                                   "patch": {"name": "x"}, "reason": "x",
                                   "base_revision": 5})
    with pytest.raises(ToolError, match="RevisionNotFound"):
        call(mcp, "rollback_asset", {"asset_id": "char_a", "to_revision": 99})


# ---------- 011 US3：移交包（MCP 面） ----------

def test_export_handoff_via_mcp(mcp, tmp_path):
    _seed_run(tmp_path / "mcp.db")
    out = tmp_path / "handoff"
    r = call(mcp, "export_handoff", {"world_id": "w_seed",
                                     "out_dir": str(out)})
    assert r.data["counts"]["events"] == 1
    assert (out / "w_seed" / "manifest.json").exists()
    # 覆盖保护
    with pytest.raises(ToolError, match="HandoffExists"):
        call(mcp, "export_handoff", {"world_id": "w_seed",
                                     "out_dir": str(out)})
    # 不存在的世界
    with pytest.raises(ToolError, match="WorldNotFound"):
        call(mcp, "export_handoff", {"world_id": "ghost",
                                     "out_dir": str(tmp_path / "h2")})


# ---------- 011 US4：版号锚点与重拍 ----------

def test_create_world_freezes_revision_pins(mcp):
    call(mcp, "create_world", {"world_id": "w1", "character_ids": ["char_a"],
                               "location_id": "scene_x"})
    call(mcp, "revise_asset", {"asset_id": "char_a",
                               "patch": {"name": "甲改"}, "reason": "改名"})
    # 世界 config 冻结的是建世界时的 rev0
    r = call(mcp, "get_asset", {"asset_id": "char_a"})
    assert r.data["current_revision"] == 1  # 当前版已前移
    # run_simulation 仍按 pin 用旧卡（事件里角色名仍是"甲"）
    call(mcp, "run_simulation", {"world_id": "w1", "run_id": "run1",
                                 "ticks": 3, "backend": "mock"})
    r = call(mcp, "get_events", {"run_id": "run1"})
    contents = json.dumps(r.data["events"], ensure_ascii=False)
    assert "甲改" not in contents and "甲" in contents


def test_reshoot_original_and_latest(mcp):
    call(mcp, "create_world", {"world_id": "w1", "character_ids": ["char_a"],
                               "location_id": "scene_x"})
    call(mcp, "run_simulation", {"world_id": "w1", "run_id": "run1",
                                 "ticks": 2, "backend": "mock"})
    # 原样重拍：pin 不变
    r = call(mcp, "reshoot", {"world_id": "w1", "new_run_id": "run2",
                              "ticks": 2, "backend": "mock"})
    assert r.data["revision_pins"]["char_a"] == 0
    # 修订后用 use_latest 重拍：新 run 用新卡
    call(mcp, "revise_asset", {"asset_id": "char_a",
                               "patch": {"name": "甲改"}, "reason": "改名"})
    r = call(mcp, "reshoot", {"world_id": "w1", "new_run_id": "run3",
                              "ticks": 2, "backend": "mock",
                              "use_latest": True})
    assert r.data["revision_pins"]["char_a"] == 1
    r = call(mcp, "get_events", {"run_id": "run3"})
    assert "甲改" in json.dumps(r.data["events"], ensure_ascii=False)
    # 三版并存，event_id 全局连续零冲突
    ids = []
    for run in ("run1", "run2", "run3"):
        ids += [e["event_id"]
                for e in call(mcp, "get_events", {"run_id": run}).data["events"]]
    assert len(ids) == len(set(ids))


def test_reshoot_errors(mcp):
    with pytest.raises(ToolError, match="WorldNotFound"):
        call(mcp, "reshoot", {"world_id": "ghost", "new_run_id": "r",
                              "ticks": 1, "backend": "mock"})
    call(mcp, "create_world", {"world_id": "w1", "character_ids": ["char_a"],
                               "location_id": "scene_x"})
    call(mcp, "run_simulation", {"world_id": "w1", "run_id": "run1",
                                 "ticks": 1, "backend": "mock"})
    with pytest.raises(ToolError, match="RunExists"):
        call(mcp, "reshoot", {"world_id": "w1", "new_run_id": "run1",
                              "ticks": 1, "backend": "mock"})


def test_run_simulation_dm_false_compat_anchor(mcp):
    """dm 缺省（False）时返回键与 007 版一致（FR-013 兼容锚点）。"""
    call(mcp, "create_world", {"world_id": "w1", "character_ids": ["char_a"],
                               "location_id": "scene_x"})
    r = call(mcp, "run_simulation", {"world_id": "w1", "run_id": "run1",
                                     "ticks": 1, "backend": "mock"})
    assert set(r.data) == {"run_id", "event_count", "ticks", "cost_tokens"}


def test_run_simulation_dm_true_offline(mcp, monkeypatch):
    """dm=True 但不构造真实 provider（monkeypatch 假裁决器），返回带裁决计数。"""
    from worldseed.dm.providers.mock import MockDMProvider
    from worldseed.protocol.dm import DMResponse
    from orchestrator import world as world_mod

    monkeypatch.setattr(
        world_mod, "build_dm_provider",
        lambda options: MockDMProvider(responses={
            "act": DMResponse(narrative="测试裁决", effects=[])}))
    call(mcp, "create_world", {"world_id": "w1", "character_ids": ["char_a"],
                               "location_id": "scene_x"})
    r = call(mcp, "run_simulation", {"world_id": "w1", "run_id": "run1",
                                     "ticks": 1, "backend": "mock",
                                     "dm": True})
    assert r.data["dm_calls"] == 1  # tick1 mock 剧本出一个 act
    assert r.data["dm_failed"] == 0


# ---------- 011 FR-014：立项调研（MCP 面，mock 接缝零外部调用） ----------

def test_research_brief_via_mcp(mcp, monkeypatch):
    import orchestrator.brief as brief_mod

    monkeypatch.setattr(brief_mod, "generate_brief",
                        lambda theme, **kw: {"theme": theme, "items": [
                            {"query": "q1", "category": "character",
                             "asset_type": "character"}]})
    monkeypatch.setattr(brief_mod, "execute_brief",
                        lambda brief, store, **kw: [
                            {"query": "q1", "category": "character",
                             "status": "stored", "asset_id": "char_x",
                             "reason": None}])
    r = call(mcp, "research_brief", {"theme": "南宋谍战"})
    assert r.data["brief"]["theme"] == "南宋谍战"
    assert r.data["ledger"][0]["status"] == "stored"


def test_research_brief_failure_readable(mcp, monkeypatch):
    import orchestrator.brief as brief_mod

    def boom(theme, **kw):
        raise ConnectionError("gptr-mcp unreachable")
    monkeypatch.setattr(brief_mod, "generate_brief", boom)
    with pytest.raises(ToolError, match="ConnectionError"):
        call(mcp, "research_brief", {"theme": "x"})


# ---------- 012 US2：幕间记忆（MCP 面） ----------

def test_interlude_memory_generate_and_read(mcp):
    # 种 run + 事件（含内心戏与定向私语）
    from db.init_db import init as init_db
    import os
    db = os.environ["NARRATIVE_DB"]
    init_db(db)
    s = Store(db)
    s.create_run("run1", "w1")
    for eid, etype, chars, content, extra in [
        ("e0001", "dialogue", ["char_a"], "甲说：诸位久候", {}),
        ("e0002", "inner_voice", ["char_a"], "甲心想：这局冲我来", {}),
        ("e0003", "dialogue", ["char_b"], "乙悄声对甲说：小心",
         {"visible_to": ["char_a", "char_b"]}),
    ]:
        e = {"event_id": eid, "run_id": "run1", "tick": 1, "seq": 0,
             "type": etype, "characters": chars, "location": "scene_x",
             "content": content, "emotion": "", "cause_refs": [],
             "shot_hint": {"camera": "medium", "duration_s": 3.0},
             "created_at": "2026-10-21T00:00:00+00:00", **extra}
        s.put_event(e)
    s.finish_run("run1", "done")
    s.close()

    r = call(mcp, "generate_interlude_memory",
             {"run_id": "run1", "character_ids": ["char_a", "char_b"],
              "channel": "template"})
    mems = {m["asset_id"]: m for m in r.data["memories"]}
    assert mems["char_a"]["reused"] is False
    assert "这局冲我来" in mems["char_a"]["summary"]
    assert "这局冲我来" not in mems["char_b"]["summary"]  # 零泄漏

    # 幂等复用：tokens=0 且 reused=True（SC-003）
    r = call(mcp, "generate_interlude_memory",
             {"run_id": "run1", "character_ids": ["char_a"]})
    assert r.data["memories"][0]["reused"] is True
    assert r.data["memories"][0]["tokens_in"] == 0

    # 读取：字段完整（SC-005）
    r = call(mcp, "get_interlude_memory", {"run_id": "run1"})
    m = r.data["memories"][0]
    for k in ("asset_id", "revision", "summary", "event_refs", "channel",
              "tokens_in", "tokens_out", "created_at"):
        assert k in m, k
    r = call(mcp, "get_interlude_memory",
             {"run_id": "run1", "asset_id": "char_a"})
    assert len(r.data["memories"]) == 1


def test_interlude_memory_errors(mcp):
    with pytest.raises(ToolError, match="RunNotFound"):
        call(mcp, "generate_interlude_memory",
             {"run_id": "ghost", "character_ids": ["char_a"]})
    _seed_minimal_run(mcp)
    with pytest.raises(ToolError, match="BadChannel"):
        call(mcp, "generate_interlude_memory",
             {"run_id": "run1", "character_ids": ["char_a"],
              "channel": "magic"})


def _seed_minimal_run(mcp):
    import os
    from db.init_db import init as init_db
    db = os.environ["NARRATIVE_DB"]
    init_db(db)
    s = Store(db)
    s.create_run("run1", "w1")
    s.finish_run("run1", "done")
    s.close()


# ---------- 012 US3：memory_from 接线（MCP 三工具） ----------

def test_memory_from_wired_through_tools(mcp):
    import os
    from db.init_db import init as init_db
    db = os.environ["NARRATIVE_DB"]
    init_db(db)
    s = Store(db)
    s.create_run("run_prev", "w_prev")
    s.finish_run("run_prev", "done")
    s.put_memory("run_prev", "char_a", "上一幕记忆甲", ["e0001"], "template")
    s.close()

    # create_world 冻结 memory_from
    r = call(mcp, "create_world", {"world_id": "w2",
                                   "character_ids": ["char_a"],
                                   "location_id": "scene_x",
                                   "memory_from": "run_prev"})
    assert r.data["world_id"] == "w2"

    # run_simulation 缺省沿用 config 冻结的 memory_from（不报错即通路）
    r = call(mcp, "run_simulation", {"world_id": "w2", "run_id": "run2",
                                     "ticks": 1, "backend": "mock"})
    assert r.data["event_count"] == 2  # 1 开场 + 1 tick

    # reshoot 沿用同一冻结记忆来源
    r = call(mcp, "reshoot", {"world_id": "w2", "new_run_id": "run3",
                              "ticks": 1, "backend": "mock"})
    assert r.data["run_id"] == "run3"
    # 显式传来源（覆盖参数通路）
    r = call(mcp, "reshoot", {"world_id": "w2", "new_run_id": "run4",
                              "ticks": 1, "backend": "mock",
                              "memory_from": "run_prev"})
    assert r.data["run_id"] == "run4"


# ---------- 存量资产 pin 回归（真机发现的缺口） ----------

def test_legacy_asset_pin_resolvable(mcp):
    """011 前入库的资产（无修订行）：create_world 自动补建 rev0，pin 可解析。"""
    import os
    from db.init_db import init as init_db
    db = os.environ["NARRATIVE_DB"]
    init_db(db)
    s = Store(db)
    # 模拟存量：删掉全部修订行
    s._conn.execute("DELETE FROM asset_revisions")
    s._conn.commit()
    s.close()

    call(mcp, "create_world", {"world_id": "w_leg",
                               "character_ids": ["char_a"],
                               "location_id": "scene_x"})
    r = call(mcp, "run_simulation", {"world_id": "w_leg", "run_id": "r_leg",
                                     "ticks": 1, "backend": "mock"})
    assert r.data["event_count"] == 2
