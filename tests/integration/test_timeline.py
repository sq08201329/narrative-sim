"""023 集成测试：import → research → world → run → export 全链（离线注入）。"""
import hashlib
import json
import re

import pytest

from db.init_db import init as init_db
from orchestrator import story_tree as st
from orchestrator import workflows
from orchestrator.store import Store
from tests.contract.test_story_tree import STORY, fake_chat

PROV = {"researched_at": "t", "retriever": "test", "model": "test", "confidence": 0.5}


def fake_research(query, asset_type, store):
    prefix = {"character": "char", "scene": "scene", "prop": "prop"}[asset_type]
    aid = f"{prefix}_{hashlib.sha1(query.encode()).hexdigest()[:8]}"
    asset = {"asset_id": aid, "type": asset_type, "name": query,
             "provenance": dict(PROV), "status": "verified"}
    if asset_type == "character":
        asset["appearance"] = {"visual_prompt": "a person"}
        asset["persona_spec"] = {
            "age": 30, "occupation": "旅人", "personality": "沉稳",
            "beliefs": "守密", "speech_style": "简短", "goals": [],
        }
    else:
        asset["appearance"] = {"visual_prompt": "a place", "description": query}
    store.put_asset(asset)
    return aid


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "timeline.db")
    init_db(path)
    return path


def test_import_show_export(db, tmp_path):
    r = workflows.import_timeline(db, "T001", STORY, chat_json_fn=fake_chat)
    assert r["status"] == "ready" and r["node_count"] == 4
    assert all(c["passed"] for c in r["checks"])

    tree = workflows.show_timeline(db, "T001")
    assert tree["tree_id"] == "T001" and tree["self_check"]["passed"]

    out = str(tmp_path / "tree.json")
    exp = workflows.export_timeline(db, "T001", out)
    assert exp["node_count"] == 4
    assert json.loads(open(out, encoding="utf-8").read())["tree_id"] == "T001"

    with pytest.raises(workflows.TreeNotFound):
        workflows.show_timeline(db, "NOPE")


def test_import_duplicate_requires_overwrite(db):
    workflows.import_timeline(db, "T001", STORY, chat_json_fn=fake_chat)
    with pytest.raises(ValueError, match="已存在"):
        workflows.import_timeline(db, "T001", STORY, chat_json_fn=fake_chat)
    assert workflows.import_timeline(db, "T001", STORY, overwrite=True,
                                     chat_json_fn=fake_chat)["node_count"] == 4


def test_full_chain(db, tmp_path):
    tree = st.parse_story(STORY, "T001", chat_json_fn=fake_chat)
    store = Store(db)
    store.put_tree(tree)
    store.close()

    r = workflows.drive_timeline(db, "T001", "research", research_asset_fn=fake_research)
    assert r["ledger"] and all(e.get("asset_id") for e in r["ledger"])
    assert len(r["entity_assets"]) == 5  # 李四/张三/临安酒楼/城门/蜡丸

    w = workflows.drive_timeline(db, "T001", "world", world_id="W001")
    assert len(w["worlds"]) == 2
    assert all(x["world_id"].startswith("W001__") for x in w["worlds"])

    run = workflows.drive_timeline(db, "T001", "run", run_id="R001",
                                   backend="mock", ticks=6)
    assert len(run["runs"]) == 2
    assert all(x["event_count"] > 0 for x in run["runs"])

    store = Store(db)
    tree2 = store.get_tree("T001")
    assert set(tree2["run_nodes"]) == {x["run_id"] for x in run["runs"]}
    for rid in tree2["run_nodes"]:
        events = store.export_events(rid)
        assert events
        assert all(re.match(r"^n[0-9]{4,}$", e["node_id"]) for e in events)
        keys = [(e["node_id"], e["tick"], e["seq"]) for e in events]
        assert keys == sorted(keys)
    store.close()

    out = str(tmp_path / "R001.jsonl")
    exp = workflows.export_events(db, run["runs"][0]["run_id"], out)
    assert exp["count"] > 0


def test_drive_rejects_missing_tree(db):
    with pytest.raises(workflows.TreeNotFound):
        workflows.drive_timeline(db, "NOPE", "research")


def test_cli_timeline_surface(tmp_path, monkeypatch):
    from orchestrator import cli

    args = cli.build_parser().parse_args(
        ["timeline", "drive", "T001", "--stage", "world", "--world-id", "W001"])
    assert args.command == "timeline" and args.stage == "world"

    seen = {}

    def fake_import(db, tid, text, **kw):
        seen["args"] = (db, tid, text, kw)
        return {"tree_id": tid, "status": "ready", "node_count": 4, "checks": []}

    from orchestrator import workflows as wf
    monkeypatch.setattr(wf, "import_timeline", fake_import)
    story = tmp_path / "s.txt"
    story.write_text(STORY, encoding="utf-8")
    db = tmp_path / "c.db"
    rc = cli.main(["--home", str(tmp_path / "home"), "--db", str(db),
                   "timeline", "import", "T001", "--story", str(story)])
    assert rc == 0 and seen["args"][1] == "T001"


def test_mcp_timeline_tools(tmp_path, monkeypatch):
    import asyncio
    from fastmcp import Client
    import orchestrator.mcp_server as mcp_mod

    monkeypatch.setenv("NARRATIVE_DB", str(tmp_path / "m.db"))

    def fake_import(db, tid, text, **kw):
        return {"tree_id": tid, "status": "ready", "node_count": 4, "checks": []}

    monkeypatch.setattr(mcp_mod.workflows, "import_timeline", fake_import)
    server = mcp_mod.build_server()

    async def go():
        async with Client(server) as c:
            names = {t.name for t in await c.list_tools()}
            assert {"import_timeline", "show_timeline", "drive_timeline"} <= names
            r = await c.call_tool(
                "import_timeline", {"tree_id": "T001", "story_text": STORY})
            return r.data

    assert asyncio.run(go())["status"] == "ready"


def test_drive_rejects_unready_tree(db, monkeypatch):
    from orchestrator.store import Store

    tree = st.parse_story(STORY, "T001", chat_json_fn=fake_chat)
    tree["self_check"]["passed"] = False
    writes = []
    monkeypatch.setattr(Store, "get_tree",
                        lambda self, tid: tree if tid == "T001" else None)
    monkeypatch.setattr(Store, "put_tree",
                        lambda self, t, **kw: writes.append(t["tree_id"]))
    with pytest.raises(st.TreeError, match="未就绪"):
        workflows.drive_timeline(db, "T001", "research", research_asset_fn=fake_research)
    assert writes == []
