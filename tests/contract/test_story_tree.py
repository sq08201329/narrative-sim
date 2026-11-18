"""023 契约测试：story_tree schema、四项自查、单一入口与 M1 不回归。"""
import hashlib

import pytest

from orchestrator import story_tree as st


STORY = (
    "午后，李四走入临安酒楼。张三已在二楼等候。"
    "李四取出蜡丸递给张三。三日后的清晨，两人在城门分手。"
)


def fake_chat(messages):
    return {"nodes": [
        {"ord": 1, "text_time": "午后", "location_name": "临安酒楼",
         "character_names": ["李四"], "prop_names": [],
         "event": {"type": "action", "summary": "李四走入酒楼"},
         "quote": "午后，李四走入临安酒楼。"},
        {"ord": 2, "text_time": None, "location_name": None,
         "character_names": ["张三"], "prop_names": [],
         "event": {"type": "action", "summary": "张三在二楼等候"},
         "quote": "张三已在二楼等候。"},
        {"ord": 3, "text_time": None, "location_name": None,
         "character_names": ["李四", "张三"], "prop_names": ["蜡丸"],
         "event": {"type": "action", "summary": "李四递蜡丸给张三"},
         "quote": "李四取出蜡丸递给张三。"},
        {"ord": 4, "text_time": "三日后的清晨", "location_name": "城门",
         "character_names": ["李四", "张三"], "prop_names": [],
         "event": {"type": "action", "summary": "两人在城门分手"},
         "quote": "三日后的清晨，两人在城门分手。"},
    ]}


def test_parse_story_self_check_passes():
    tree = st.parse_story(STORY, "T001", chat_json_fn=fake_chat)
    assert tree["status"] == "ready"
    assert tree["self_check"]["passed"] is True
    assert [c["name"] for c in tree["self_check"]["checks"]] == list(st.CHECK_NAMES)
    assert all(c["passed"] for c in tree["self_check"]["checks"])
    assert tree["source_sha256"] == hashlib.sha256(STORY.encode()).hexdigest()
    assert len(tree["nodes"]) == 4
    assert [n["ord"] for n in tree["nodes"]] == [1, 2, 3, 4]
    # 规范名去重：李四/张三只各一条 character 实体
    names = [e["name"] for e in tree["entities"] if e["type"] == "character"]
    assert names.count("李四") == 1 and names.count("张三") == 1


def test_source_span_verbatim():
    tree = st.parse_story(STORY, "T002", chat_json_fn=fake_chat)
    for node in tree["nodes"]:
        s = node["source_span"]
        assert STORY[s["start"]:s["end"]] == s["quote"]


def test_quote_drift_fails_self_check_and_retries():
    calls = []

    def bad_chat(messages):
        calls.append(1)
        raw = fake_chat(messages)
        raw["nodes"][1]["quote"] = "这句不在原文里。"
        return raw

    with pytest.raises(st.TreeError):
        st.parse_story(STORY, "T003", chat_json_fn=bad_chat)
    assert len(calls) == 2  # 失败后重试一次


def test_no_fabricated_time():
    def chat(messages):
        raw = fake_chat(messages)
        raw["nodes"][0]["text_time"] = "编造的纪年"
        return raw
    tree = st.parse_story(STORY, "T004", chat_json_fn=chat)
    assert tree["nodes"][0]["text_time"] is None


def test_map_nodes_to_ticks():
    tree = st.parse_story(STORY, "T005", chat_json_fn=fake_chat)
    mapping = st.map_nodes_to_ticks(tree["nodes"], 6)
    assert mapping[0] == "n0001"
    assert set(mapping.values()) == {n["node_id"] for n in tree["nodes"]}
    with pytest.raises(st.TreeError):
        st.map_nodes_to_ticks(tree["nodes"], 2)


def test_build_research_brief_and_world_specs():
    tree = st.parse_story(STORY, "T006", chat_json_fn=fake_chat)
    brief = st.build_research_brief(tree)
    assert {i["category"] for i in brief["items"]} == {"character", "world"}
    # 角色名去重：一个李四 + 一个张三
    chars = [i["query"] for i in brief["items"] if i["category"] == "character"]
    assert sorted(chars) == ["张三", "李四"]
    assets = {e["key"]: f"{e['type']}_{e['name']}" for e in tree["entities"]}
    specs = st.build_world_specs(tree, assets, "W001")
    assert len(specs) == 2  # 临安酒楼 + 城门
    assert all(s["world_id"].startswith("W001__") for s in specs)
    # 缺省 location 沿用上一个节点：节点 2/3 归到酒楼世界
    assert specs[0]["node_ids"] == ["n0001", "n0002", "n0003"]


def test_export_events_legacy_order_without_node_id(tmp_path):
    from datetime import datetime, timezone
    from db.init_db import init as init_db
    from orchestrator.store import Store

    db = str(tmp_path / "legacy.db")
    init_db(db)
    store = Store(db)
    store.create_run("R0", "W0")

    def ev(eid, tick, seq):
        return {
            "event_id": eid, "run_id": "R0", "tick": tick, "seq": seq,
            "type": "action", "characters": ["char_a"], "location": "scene_a",
            "content": "x", "cause_refs": [],
            "shot_hint": {"camera": "wide", "duration_s": 3.0},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    for item in [ev("e0001", 1, 2), ev("e0002", 1, 1), ev("e0003", 0, 0)]:
        store.put_event(item)
    out = store.export_events("R0")
    assert [(e["tick"], e["seq"]) for e in out] == [(0, 0), (1, 1), (1, 2)]
    assert all("node_id" not in e for e in out)
    store.close()
