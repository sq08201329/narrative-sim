"""US2 契约守卫：非法数据必须被明确拒绝且不落库。

覆盖 spec：FR-006 / SC-003；错误格式见 contracts/asset-event-schemas.md。
"""
import pytest

from db.init_db import init as init_db
from orchestrator.store import SchemaValidationError, Store

VALID_ASSET = {
    "asset_id": "char_test_guard",
    "type": "character",
    "name": "守卫测试角色",
    "appearance": {"visual_prompt": "a test character"},
    "persona_spec": {
        "age": 30, "occupation": "测试", "personality": "冷静",
        "beliefs": "无", "speech_style": "平实",
    },
    "provenance": {
        "researched_at": "2026-10-19T00:00:00+00:00", "retriever": "test",
        "model": "none", "confidence": 0.5,
    },
}

VALID_EVENT = {
    "event_id": "e0001", "run_id": "guard_run", "tick": 1, "seq": 1,
    "type": "dialogue", "characters": ["char_test_guard"],
    "location": "scene_test_hall", "content": "测试台词", "cause_refs": [],
    "shot_hint": {"camera": "medium", "duration_s": 3.0},
    "created_at": "2026-10-19T00:00:00+00:00",
}


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "guard.db"
    init_db(str(db))
    s = Store(str(db))
    yield s
    s.close()


def _asset_absent(store: Store, asset_id: str) -> bool:
    try:
        store.get_asset(asset_id)
    except KeyError:
        return True
    return False


def test_asset_missing_required_field_rejected(store):
    bad = {k: v for k, v in VALID_ASSET.items() if k != "provenance"}
    with pytest.raises(SchemaValidationError, match=r"asset\.schema\.json 校验失败: \$"):
        store.put_asset(bad)
    assert _asset_absent(store, "char_test_guard")


def test_asset_bad_id_pattern_rejected(store):
    bad = dict(VALID_ASSET, asset_id="角色甲")
    with pytest.raises(SchemaValidationError, match="asset_id"):
        store.put_asset(bad)
    assert _asset_absent(store, "char_test_guard")


def test_character_without_persona_spec_rejected(store):
    bad = {k: v for k, v in VALID_ASSET.items() if k != "persona_spec"}
    with pytest.raises(SchemaValidationError, match="persona_spec"):
        store.put_asset(bad)


def test_event_bad_type_rejected(store):
    store.put_asset(VALID_ASSET)
    store.create_run("guard_run", "world_guard")
    bad = dict(VALID_EVENT, type="monologue")
    with pytest.raises(SchemaValidationError, match="event\.schema\.json 校验失败"):
        store.put_event(bad)
    assert store.export_events("guard_run") == []


def test_duplicate_run_id_rejected(store):
    store.create_run("guard_run", "world_guard")
    with pytest.raises(ValueError, match="run_id 已存在"):
        store.create_run("guard_run", "world_guard")


def test_error_message_contains_json_path(store):
    bad = {k: v for k, v in VALID_ASSET.items() if k != "name"}
    with pytest.raises(SchemaValidationError) as exc_info:
        store.put_asset(bad)
    assert "'name' is a required property" in str(exc_info.value)
