"""010 离线测试：DM 裁判启用（真实引擎 + MockDMProvider，零 LLM 调用）。

覆盖：dm_calls 审计表（T003）/ 配置注入与兼容锚点（T004）/
裁决效果与审计（T007）/ 故障降级（T011）/ 史料注入（T009）。
"""
import json

import pytest

from db.init_db import init as init_db
from orchestrator.persona import MockPersonaBackend
from orchestrator.store import Store
from orchestrator.world import build_scene_config, run_world

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


# ---------- T003：dm_calls 审计表 ----------

def test_dm_calls_roundtrip(store):
    store.create_run("r1", "w1")
    row_id = store.put_dm_call(
        "r1", 2, "act", "char_a", '{"description": "偷听"}',
        "判定偷听结果", "甲被察觉了", '[{"operator": "set"}]',
        120, 30, 1.5, False,
    )
    assert row_id == 1
    rows = store.list_dm_calls("r1")
    assert len(rows) == 1
    r = rows[0]
    assert r["tick"] == 2 and r["action"] == "act" and r["agent_id"] == "char_a"
    assert r["tokens_in"] == 120 and r["tokens_out"] == 30
    assert r["elapsed_s"] == 1.5 and r["failed"] == 0
    # 失败行：failed=1 且 effects 为 []
    store.put_dm_call("r1", 3, "act", "char_b", "{}", "", "(DM failed)",
                      "[]", 0, 0, 0.2, True)
    rows = store.list_dm_calls("r1")
    assert len(rows) == 2  # 按 id 升序
    assert rows[1]["failed"] == 1 and rows[1]["effects"] == "[]"
    # 空 run
    assert store.list_dm_calls("r_ghost") == []


# ---------- T004：配置注入与兼容锚点 ----------

def test_compat_anchor_dm_none(store):
    """dm=None（默认）时输出与 006 版逐键一致：无 dm/dm_knowledge/max_dm_calls。"""
    cfg = build_scene_config(store, ["char_a", "char_b"], "scene_hall")
    for verb in ("say", "whisper", "act"):
        assert "dm" not in cfg["actions"][verb]
    assert "dm_knowledge" not in cfg["scene"]
    assert "max_dm_calls" not in cfg["scene"]


def test_dm_options_inject(store):
    from orchestrator.world import DMOptions

    cfg = build_scene_config(store, ["char_a", "char_b"], "scene_hall",
                             dm=DMOptions())
    # 仅 act 挂裁决；say/whisper 是确定性通讯
    assert "dm" not in cfg["actions"]["say"]
    assert "dm" not in cfg["actions"]["whisper"]
    dm_cfg = cfg["actions"]["act"]["dm"]
    assert dm_cfg["hint"]
    assert set(dm_cfg["allowed_ops"]) == {"set", "increment", "decrement",
                                          "emit_event"}
    assert dm_cfg["max_effects"] == 5
    # 成本帽生效
    assert cfg["scene"]["max_dm_calls"] == 50
    # 引擎 schema 校验通过（真实校验器）
    from orchestrator.world import _make_engine
    engine, _ = _make_engine(cfg)
    assert engine is not None


def test_build_dm_provider_no_keys(monkeypatch):
    from orchestrator.dm import DMConfigError, build_dm_provider
    from orchestrator.world import DMOptions

    for var in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
                "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(DMConfigError, match="DEEPSEEK_API_KEY"):
        build_dm_provider(DMOptions())


def test_bridge_never_overrides_openai(monkeypatch):
    from orchestrator.dm import build_dm_provider
    from orchestrator.world import DMOptions
    import os

    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPENAI_API_KEY", "existing-openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://existing.example.com")
    provider = build_dm_provider(DMOptions())
    assert provider is not None
    # 已有 OPENAI_* 不被覆盖
    assert os.environ["OPENAI_API_KEY"] == "existing-openai"
    assert os.environ["OPENAI_BASE_URL"] == "https://existing.example.com"


def test_bridge_maps_deepseek(monkeypatch):
    from orchestrator.dm import build_dm_provider
    from orchestrator.world import DMOptions
    import os

    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    build_dm_provider(DMOptions())
    assert os.environ["OPENAI_API_KEY"] == "ds-key"
    assert os.environ["OPENAI_BASE_URL"] == "https://api.deepseek.com"


# ---------- T004/T007：裁决主链路（MockDMProvider 驱动真实引擎） ----------

def _mock_dm(narrative="甲的偷听被察觉了。", effects=None):
    from worldseed.dm.providers.mock import MockDMProvider
    from worldseed.protocol.dm import DMResponse

    return MockDMProvider(responses={
        "act": DMResponse(narrative=narrative, effects=effects or []),
    })


def test_act_adjudicated_effects_and_audit(store):
    """act 动作触发裁决：效果落世界状态快照，审计行进 dm_calls。"""
    from worldseed.models.config_schema import EffectConfig
    from orchestrator.world import DMOptions

    dm_provider = _mock_dm(effects=[EffectConfig(
        operator="set", target="char_a.exposure", value="已暴露")])
    run_world(store, "r1", "w1", ["char_a", "char_b"], "scene_hall",
              ticks=1, backend=MockPersonaBackend(),
              dm=DMOptions(), dm_provider=dm_provider)
    # tick1 Mock 后端每角色出一个 action 类动作 → 2 次裁决
    calls = store.list_dm_calls("r1")
    assert len(calls) == 2
    for c in calls:
        assert c["action"] == "act" and c["failed"] == 0
        assert c["narrative"] == "甲的偷听被察觉了。"
        effects = json.loads(c["effects"])
        assert effects and effects[0]["operator"] == "set"
    # 效果落入快照（实体属性为扁平结构）
    _, state_json = store.get_world_state("w1")
    state = json.loads(state_json)
    entities = {e["id"]: e for e in state["entities"]}
    assert entities["char_a"].get("exposure") == "已暴露"


def test_say_not_adjudicated(store):
    """say/whisper 不挂裁决：dialogue tick 不产生 dm_calls。"""
    from orchestrator.world import DMOptions

    dm_provider = _mock_dm()
    run_world(store, "r1", "w1", ["char_a", "char_b"], "scene_hall",
              ticks=3, backend=MockPersonaBackend(),
              dm=DMOptions(), dm_provider=dm_provider)
    calls = store.list_dm_calls("r1")
    # tick1 act×2 裁决；tick2 inner_voice 不进引擎；tick3 dialogue→say 不裁决
    assert len(calls) == 2
    assert dm_provider.call_count == 2


# ---------- T009：史料注入 ----------

def test_build_dm_knowledge_budget(store):
    from orchestrator.dm import build_dm_knowledge

    store.put_material("char_a", "皇城司侦缉手段", "test", "甲" * 300)
    store.put_material("char_a", "临安夜市", "test", "乙" * 300)
    store.put_material("scene_hall", "酒楼布局", "test", "丙" * 300)
    knowledge = build_dm_knowledge(
        store, ["char_a", "char_b", "scene_hall"], budget=2000)
    assert "【皇城司侦缉手段】" in knowledge
    assert "【酒楼布局】" in knowledge
    assert len(knowledge) <= 2000
    # char_b 无原料不抛异常
    # 小预算：尾部整条丢弃
    small = build_dm_knowledge(store, ["char_a"], budget=100)
    assert small == ""
    # 无原料
    assert build_dm_knowledge(store, ["char_b"]) == ""


def test_dm_knowledge_injected_into_scene(store):
    from orchestrator.world import DMOptions

    store.put_material("char_a", "皇城司侦缉手段", "test", "察子善伏于暗处")
    cfg = build_scene_config(store, ["char_a", "char_b"], "scene_hall",
                             dm=DMOptions())
    assert "【皇城司侦缉手段】察子善伏于暗处" in cfg["scene"]["dm_knowledge"]
    # 引擎 schema 校验通过
    from orchestrator.world import _make_engine
    engine, _ = _make_engine(cfg, dm_provider=_mock_dm())
    assert engine is not None


# ---------- T011：故障降级 ----------

def test_dm_failure_degrades_without_crash(store):
    """裁决连续失败：run 正常结束，dm_calls 全 failed=1，事件流含兜底。"""
    from worldseed.dm.providers.mock import FailingMockDMProvider
    from worldseed.protocol.dm import DMResponse
    from orchestrator.world import DMOptions

    dm_provider = FailingMockDMProvider(
        fail_count=999,
        success_response=DMResponse(narrative="不会到达"),
    )
    events = run_world(store, "r1", "w1", ["char_a", "char_b"], "scene_hall",
                       ticks=1, backend=MockPersonaBackend(),
                       dm=DMOptions(), dm_provider=dm_provider)
    calls = store.list_dm_calls("r1")
    assert len(calls) == 2  # 两个角色的 act 各裁决一次（重试耗尽后降级）
    assert all(c["failed"] == 1 for c in calls)
    assert all(c["effects"] == "[]" for c in calls)
    # run 完成（未抛异常即达成）；事件流正常产出
    assert events and events[0]["type"] == "scene_change"
    # 引擎对每个 act 重试 max_attempts=2
    assert dm_provider.call_count == 4
