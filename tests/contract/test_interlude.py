"""012 离线测试：幕间记忆传递（零外部调用）。

覆盖：存储原语（T004）/ 过滤三规则与 template 通道（T005）/ 注入两路与
兼容锚点（T006）/ llm 通道与预算（T012）。
"""
import json

import pytest

from db.init_db import init as init_db
from orchestrator.store import Store

SCENE = {
    "asset_id": "scene_hall", "type": "scene", "name": "临河酒楼",
    "appearance": {"visual_prompt": "tavern", "description": "临河"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}


def _char(asset_id: str, name: str) -> dict:
    return {
        "asset_id": asset_id, "type": "character", "name": name,
        "appearance": {"visual_prompt": f"{name} look"},
        "persona_spec": {"age": 30, "occupation": "旅人", "personality": "沉稳",
                         "beliefs": "各扫门前雪", "speech_style": "简短",
                         "secret": f"{name}的秘密"},
        "provenance": {"researched_at": "t", "retriever": "test",
                       "model": "test", "confidence": 0.5},
    }


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    s = Store(db)
    s.put_asset(SCENE)
    s.put_asset(_char("char_a", "甲"))
    s.put_asset(_char("char_b", "乙"))
    s.put_asset(_char("char_c", "丙"))
    yield s
    s.close()


def _event(eid, run, tick, etype, chars, content, **extra):
    e = {
        "event_id": eid, "run_id": run, "tick": tick, "seq": 0,
        "type": etype, "characters": chars, "location": "scene_hall",
        "content": content, "emotion": "", "cause_refs": [],
        "shot_hint": {"camera": "medium", "duration_s": 3.0},
        "created_at": "2026-10-21T00:00:00+00:00",
    }
    e.update(extra)
    return e


@pytest.fixture()
def store_with_run(store):
    """上一幕 run1：公开对话 + 甲的内心 + 甲乙定向私语。"""
    store.create_run("run1", "w1")
    store.put_event(_event("e0001", "run1", 0, "scene_change",
                           ["char_a", "char_b", "char_c"], "开场"))
    store.put_event(_event("e0002", "run1", 1, "dialogue", ["char_a"],
                           "甲说：诸位久候"))
    store.put_event(_event("e0003", "run1", 1, "inner_voice", ["char_a"],
                           "甲心想：这局冲我来"))
    store.put_event(_event("e0004", "run1", 2, "dialogue", ["char_b"],
                           "乙悄声对甲说：小心丙",
                           visible_to=["char_a", "char_b"]))
    store.finish_run("run1", "done")
    return store


# ---------- T004：存储原语 ----------

def test_memory_put_get_revision(store):
    r1 = store.put_memory("run1", "char_a", "摘要v1", ["e0001"], "template")
    assert r1 == 1
    m = store.get_memory("run1", "char_a")
    assert m["summary"] == "摘要v1" and m["event_refs"] == ["e0001"]
    # 同键再写升版，旧版留痕
    r2 = store.put_memory("run1", "char_a", "摘要v2", ["e0002"], "llm",
                          tokens_in=100, tokens_out=50)
    assert r2 == 2
    m = store.get_memory("run1", "char_a")
    assert m["summary"] == "摘要v2" and m["revision"] == 2
    assert m["tokens_in"] == 100
    # 无记录
    assert store.get_memory("run1", "char_b") is None
    assert store.list_memories("run_ghost") == []


def test_list_memories_current_only(store):
    store.put_memory("run1", "char_a", "v1", [], "template")
    store.put_memory("run1", "char_a", "v2", [], "template")
    store.put_memory("run1", "char_b", "乙v1", [], "template")
    ms = store.list_memories("run1")
    assert len(ms) == 2
    by_id = {m["asset_id"]: m for m in ms}
    assert by_id["char_a"]["summary"] == "v2"
    assert by_id["char_b"]["revision"] == 1


# ---------- T005：过滤三规则 + template 通道 ----------

def test_filter_three_rules(store_with_run):
    """SC-001：inner_voice 仅本人 / visible_to 列内 / 其余公开。"""
    from orchestrator.interlude import generate_memories

    ms = generate_memories(store_with_run, "run1",
                           ["char_a", "char_b", "char_c"],
                           channel="template")
    by_id = {m["asset_id"]: m for m in ms}

    # 甲：全部 4 条（含自己的内心戏与定向私语）
    assert set(by_id["char_a"]["event_refs"]) == {"e0001", "e0002",
                                                  "e0003", "e0004"}
    # 乙：公开 2 条 + 定向私语；无甲的内心
    assert set(by_id["char_b"]["event_refs"]) == {"e0001", "e0002", "e0004"}
    assert "这局冲我来" not in by_id["char_b"]["summary"]
    # 丙：仅公开 2 条——他人私语零泄漏
    assert set(by_id["char_c"]["event_refs"]) == {"e0001", "e0002"}
    assert "小心丙" not in by_id["char_c"]["summary"]
    # template 通道标注
    assert all(m["channel"] == "template" for m in ms)


def test_template_deterministic(store_with_run):
    from orchestrator.interlude import generate_memories
    a = generate_memories(store_with_run, "run1", ["char_a"],
                          channel="template")[0]["summary"]
    b = generate_memories(store_with_run, "run1", ["char_a"],
                          channel="template", regenerate=True)[0]["summary"]
    assert a == b
    assert a  # 非空


def test_idempotent_reuse(store_with_run):
    """同键二次生成复用库存，tokens=0，reused=True（SC-003）。"""
    from orchestrator.interlude import generate_memories
    generate_memories(store_with_run, "run1", ["char_a"], channel="template")
    ms = generate_memories(store_with_run, "run1", ["char_a"],
                           channel="template")
    assert ms[0]["reused"] is True
    assert ms[0]["revision"] == 1
    # regenerate 升版
    ms = generate_memories(store_with_run, "run1", ["char_a"],
                           channel="template", regenerate=True)
    assert ms[0]["reused"] is False and ms[0]["revision"] == 2
    # 旧版留痕
    assert store_with_run.get_memory("run1", "char_a")["revision"] == 2


def test_source_run_missing(store):
    from orchestrator.interlude import InterludeError, generate_memories
    with pytest.raises(InterludeError, match="run"):
        generate_memories(store, "run_ghost", ["char_a"])


def test_empty_run_explicit_empty(store):
    store.create_run("run_empty", "w1")
    store.finish_run("run_empty", "done")
    from orchestrator.interlude import generate_memories
    ms = generate_memories(store, "run_empty", ["char_a"], channel="template")
    assert ms[0]["summary"] == "" and ms[0]["event_refs"] == []


def test_cross_drama_intersection(store_with_run):
    """FR-009：目标角色与来源 run 取交集，差集标 skipped。"""
    from orchestrator.interlude import generate_memories
    ms = generate_memories(store_with_run, "run1",
                           ["char_a", "char_ghost"], channel="template")
    assert [m["asset_id"] for m in ms if not m.get("skipped")] == ["char_a"]
    skipped = [m for m in ms if m.get("skipped")]
    assert skipped and skipped[0]["asset_id"] == "char_ghost"


# ---------- T006：注入两路 + 兼容锚点 ----------

def test_injection_into_config_and_backend(store_with_run):
    from orchestrator.interlude import generate_memories
    from orchestrator.persona import MockPersonaBackend
    from orchestrator.world import build_scene_config, run_world

    generate_memories(store_with_run, "run1", ["char_a", "char_b"],
                      channel="template")
    backend = MockPersonaBackend()
    run_world(store_with_run, "run2", "w2", ["char_a", "char_b"],
              "scene_hall", ticks=1, backend=backend, memory_from="run1")
    # 后端路：seeded 记录与库存记忆一致
    seeded = dict(backend.seeded)
    assert "char_a" in seeded and "char_b" in seeded
    assert "这局冲我来" in seeded["char_a"]  # 本人内心可见
    assert "这局冲我来" not in seeded["char_b"]
    # 引擎路：角色卡 memory 键
    cfg = build_scene_config(store_with_run, ["char_a", "char_b"],
                             "scene_hall",
                             memories={"char_a": seeded["char_a"]})
    agents = {a["id"]: a for a in cfg["agents"]}
    assert "这局冲我来" in agents["char_a"]["character"]["memory"]
    assert "memory" not in agents["char_b"]["character"]  # 未给的不加键


def test_compat_anchor_no_memory(store):
    """不传 memory_from/memories：行为与现状逐键一致。"""
    from orchestrator.world import build_scene_config
    cfg = build_scene_config(store, ["char_a"], "scene_hall")
    assert "memory" not in cfg["agents"][0]["character"]


# ---------- T012：llm 通道与预算 + memory_from 接线 ----------

def test_llm_channel_with_mock_chat(store_with_run):
    """llm 通道经 chat 接缝（注入假 completion，零外部调用）。"""
    from orchestrator.interlude import generate_memories

    def fake_chat(prompt):
        return ("我记得自己说过客套话，还记得乙的提醒。", 120, 30)

    ms = generate_memories(store_with_run, "run1", ["char_a"],
                           channel="llm", chat=fake_chat)
    m = ms[0]
    assert m["summary"].startswith("我记得")
    assert m["tokens_in"] == 120 and m["tokens_out"] == 30
    # 落库计量
    stored = store_with_run.get_memory("run1", "char_a")
    assert stored["channel"] == "llm" and stored["tokens_in"] == 120


def test_llm_budget_recent_first(store_with_run, monkeypatch):
    """INTERLUDE_MAX_EVENTS=2：只取新近 2 条进 prompt。"""
    from orchestrator.interlude import generate_memories
    monkeypatch.setenv("INTERLUDE_MAX_EVENTS", "2")
    seen = {}

    def spy_chat(prompt):
        seen["prompt"] = prompt
        return ("摘要", 10, 5)

    generate_memories(store_with_run, "run1", ["char_a"], channel="llm",
                      chat=spy_chat)
    assert "开场" not in seen["prompt"]      # 最早的被截掉
    assert "诸位久候" not in seen["prompt"]  # 甲可见 4 条中较早的也截掉
    assert "这局冲我来" in seen["prompt"]    # 新近保留
    assert "小心丙" in seen["prompt"]


def test_llm_failure_no_partial_write(store_with_run):
    """服务失败：报错且不落半成品。"""
    from orchestrator.interlude import generate_memories

    def boom(prompt):
        raise ConnectionError("llm unreachable")

    with pytest.raises(ConnectionError):
        generate_memories(store_with_run, "run1", ["char_a"],
                          channel="llm", chat=boom)
    assert store_with_run.get_memory("run1", "char_a") is None


def test_bad_channel(store_with_run):
    from orchestrator.interlude import InterludeError, generate_memories
    with pytest.raises(InterludeError, match="BadChannel"):
        generate_memories(store_with_run, "run1", ["char_a"],
                          channel="magic")
