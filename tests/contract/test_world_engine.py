"""006 离线测试：WorldSeed 适配器（真实引擎 + MockPersonaBackend，零 LLM）。

覆盖：配置组装（T003）/ 世界循环与契约（T004）/ 信息不对称（T004）/
快照与续跑（T007）/ 翻译口径与边界（T009）。
"""
import json

import pytest
from jsonschema import validate

from db.init_db import init as init_db
from orchestrator.persona import MockPersonaBackend
from orchestrator.store import Store
from orchestrator.world import (
    WorldConfigError,
    WorldSnapshotError,
    _make_engine,
    build_scene_config,
    run_world,
)

SCENE = {
    "asset_id": "scene_hall",
    "type": "scene",
    "name": "临河酒楼",
    "appearance": {"visual_prompt": "tavern by the river",
                   "description": "两层木结构临河酒楼"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}


def _char(asset_id: str, name: str, secret: str) -> dict:
    return {
        "asset_id": asset_id,
        "type": "character",
        "name": name,
        "appearance": {"visual_prompt": f"{name} look"},
        "persona_spec": {
            "age": 30, "occupation": "旅人", "personality": "沉稳",
            "beliefs": "各扫门前雪", "speech_style": "简短",
            "secret": secret,
        },
        "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                       "confidence": 0.5},
    }


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    s = Store(db)
    s.put_asset(SCENE)
    s.put_asset(_char("char_a", "甲", "甲的秘密：他是信使"))
    s.put_asset(_char("char_b", "乙", "乙的秘密：他是暗桩"))
    yield s
    s.close()


# ---------- T003：配置组装 ----------

def test_build_config_sections(store):
    cfg = build_scene_config(store, ["char_a", "char_b"], "scene_hall")
    assert cfg["scene"]["id"] == "scene_hall"
    assert cfg["entities"][0]["type"] == "space"
    agents = {a["id"]: a for a in cfg["agents"]}
    assert agents["char_a"]["character"]["secret"] == "甲的秘密：他是信使"
    assert agents["char_a"]["location"] == "scene_hall"
    assert "secret" in cfg["perception"]["hidden_properties"]
    assert set(cfg["actions"]) == {"say", "whisper", "act"}
    # 引擎 schema 校验通过（真实校验器）
    engine, _ = _make_engine(cfg)
    assert engine is not None


def test_build_config_missing_character(store):
    with pytest.raises(WorldConfigError, match="缺少角色资产"):
        build_scene_config(store, ["char_a", "char_ghost"], "scene_hall")


def test_build_config_missing_scene(store):
    with pytest.raises(WorldConfigError, match="缺少场景资产"):
        build_scene_config(store, ["char_a"], "scene_ghost")


def test_build_config_empty_characters(store):
    with pytest.raises(WorldConfigError, match="缺少角色"):
        build_scene_config(store, [], "scene_hall")


# ---------- T004：世界循环与契约 + 信息不对称 ----------

def test_world_loop_events_contract(store):
    events = run_world(store, "r1", "w1", ["char_a", "char_b"], "scene_hall",
                       ticks=3, backend=MockPersonaBackend())
    # 1 开场 + 3 tick × 2 角色 = 7
    assert len(events) == 7
    assert events[0]["type"] == "scene_change"
    assert events[0]["shot_hint"] == {"camera": "wide", "duration_s": 3.0}
    # event_id 连续（全新库从 e0001 起）
    assert [e["event_id"] for e in events] == [f"e{i:04d}" for i in range(1, 8)]
    # dialogue 事件（Mock tick3）shot_hint 与 001 口径一致
    dialogue = [e for e in events if e["type"] == "dialogue"]
    assert dialogue and dialogue[0]["shot_hint"] == {"camera": "medium",
                                                     "duration_s": 4.0}
    # 事件经 store 契约校验（put_event 已逐条把关；导出复验）
    schema = json.loads((json.__path__[0] and open(
        "schemas/event.schema.json", encoding="utf-8").read()))
    for e in events:
        validate(e, schema)


def test_information_asymmetry(store):
    cfg = build_scene_config(store, ["char_a", "char_b"], "scene_hall")
    engine, _ = _make_engine(cfg)
    pa = engine.perceive("char_a")
    pb = engine.perceive("char_b")
    # 两名角色的视野可核验地不同：甲见乙、乙见甲，互不见自己
    assert "char_b" in pa.nearby_agents and "char_a" not in pa.nearby_agents
    assert "char_a" in pb.nearby_agents and "char_b" not in pb.nearby_agents
    # 互见对方，但 secret 不外泄（hidden_properties 生效）
    nearby_a = json.dumps(pa.nearby_agents, ensure_ascii=False)
    nearby_b = json.dumps(pb.nearby_agents, ensure_ascii=False)
    assert "char_b" in nearby_a and "char_a" in nearby_b
    assert "信使" not in nearby_a and "暗桩" not in nearby_b
    assert "secret" not in nearby_a and "secret" not in nearby_b


# ---------- T007：快照与续跑 ----------

def test_snapshot_written_each_tick(store):
    run_world(store, "r1", "w1", ["char_a", "char_b"], "scene_hall",
              ticks=3, backend=MockPersonaBackend())
    saved = store.get_world_state("w1")
    assert saved is not None
    tick, state_json = saved
    assert tick == 3
    state = json.loads(state_json)
    assert state["entities"] and state["characters"]


def test_resume_continues_without_replay(store):
    run_world(store, "r1", "w1", ["char_a", "char_b"], "scene_hall",
              ticks=3, backend=MockPersonaBackend())
    events2 = run_world(store, "r2", "w1", ["char_a", "char_b"], "scene_hall",
                        ticks=2, backend=MockPersonaBackend(), resume=True)
    # 续跑无开场事件，从 tick 4 开始
    assert all(e["tick"] >= 4 for e in events2)
    assert {e["tick"] for e in events2} == {4, 5}
    # 事件编号跨运行连续、零重复
    ids = [e["event_id"] for e in events2]
    assert ids == [f"e{i:04d}" for i in range(8, 12)]
    # 快照推进到 tick 5
    assert store.get_world_state("w1")[0] == 5


def test_resume_without_snapshot_raises(store):
    with pytest.raises(WorldSnapshotError, match="无可续跑快照"):
        run_world(store, "r1", "w_ghost", ["char_a"], "scene_hall",
                  ticks=1, backend=MockPersonaBackend(), resume=True)


def test_resume_corrupt_snapshot_raises(store):
    store.create_run("seed", "w1")
    store.put_world_state("w1", 2, "{损坏的快照")
    with pytest.raises(WorldSnapshotError, match="快照损坏"):
        run_world(store, "r1", "w1", ["char_a"], "scene_hall",
                  ticks=1, backend=MockPersonaBackend(), resume=True)


# ---------- T009：翻译口径与边界 ----------

def test_worldseed_import_boundary():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    allowed = {root / "orchestrator" / "world.py",
               root / "scripts" / "run_world_chain.py",
               root / "tests" / "contract" / "test_world_engine.py"}
    offenders = []
    for target in [root / "orchestrator", root / "scripts"]:
        for f in target.rglob("*.py"):
            if f in allowed:
                continue
            if "worldseed" in f.read_text(encoding="utf-8"):
                offenders.append(str(f.relative_to(root)))
    assert offenders == [], f"WorldSeed 接触面越界: {offenders}"
