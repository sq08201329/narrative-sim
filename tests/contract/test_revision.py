"""011 离线测试：资产修订版本化（真实 SQLite tmp 库，零外部调用）。

覆盖：存储原语（T003）/ revise/rollback 业务（T006）/ 版号锚点与重拍（T013）。
"""
import json

import pytest

from db.init_db import init as init_db
from orchestrator.store import Store

SCENE = {
    "asset_id": "scene_hall",
    "type": "scene",
    "name": "临河酒楼",
    "appearance": {"visual_prompt": "tavern by the river",
                   "description": "两层木结构临河酒楼"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}


def _char(asset_id: str, name: str, personality: str = "沉稳") -> dict:
    return {
        "asset_id": asset_id,
        "type": "character",
        "name": name,
        "appearance": {"visual_prompt": f"{name} look"},
        "persona_spec": {
            "age": 30, "occupation": "旅人", "personality": personality,
            "beliefs": "各扫门前雪", "speech_style": "简短",
            "secret": f"{name}的秘密",
        },
        "provenance": {"researched_at": "t", "retriever": "test-retriever",
                       "model": "test", "confidence": 0.5},
    }


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    s = Store(db)
    s.put_asset(SCENE)
    s.put_asset(_char("char_a", "甲"))
    yield s
    s.close()


# ---------- T003：存储原语 ----------

def test_revision0_auto_created(store):
    """put_asset 首建自动写 revision 0，author 取 provenance.retriever。"""
    revs = store.list_revisions("char_a")
    assert len(revs) == 1
    assert revs[0]["revision"] == 0
    assert revs[0]["author"] == "test-retriever"
    assert revs[0]["reason"] == "调研原版"
    assert json.loads(revs[0]["payload"])["name"] == "甲"
    assert store.current_revision("char_a") == 0


def test_put_asset_replace_auto_bump(store):
    """已有资产 REPLACE 且内容变化 → 自动升版（author=system:put_asset）。"""
    store.put_asset(_char("char_a", "甲", personality="急躁"))
    revs = store.list_revisions("char_a")
    assert len(revs) == 2
    assert revs[1]["author"] == "system:put_asset"
    assert store.current_revision("char_a") == 1
    assert store.get_asset("char_a")["persona_spec"]["personality"] == "急躁"
    # 内容不变则不升版
    store.put_asset(_char("char_a", "甲", personality="急躁"))
    assert len(store.list_revisions("char_a")) == 2


def test_pointer_payload_invariant(store):
    """不变量：assets.payload == revisions[current_revision].payload。"""
    for aid in ("char_a", "scene_hall"):
        cur = store.current_revision(aid)
        snap = store.get_revision(aid, cur)["payload"]
        current = json.loads(store._conn.execute(
            "SELECT payload FROM assets WHERE asset_id=?", (aid,)
        ).fetchone()["payload"])
        assert json.loads(snap) == current


def test_old_db_migration(tmp_path):
    """老库（无 current_revision 列、无 asset_revisions 表）init 后幂等迁移。

    用 DROP 模拟 011 之前的老库结构（经 Store 连接，不直连 sqlite3——
    宪章 III 测试守卫）。
    """
    db = tmp_path / "old.db"
    init_db(str(db))
    s = Store(str(db))
    s._conn.execute("ALTER TABLE assets DROP COLUMN current_revision")
    s._conn.execute("DROP TABLE asset_revisions")
    s._conn.execute("INSERT INTO assets(asset_id, type, name, payload)"
                    " VALUES('char_old', 'character', '老人', '{}')")
    s._conn.commit()
    s.close()

    init_db(str(db))
    s = Store(str(db))
    try:
        assert s.current_revision("char_old") == 0
        # 老资产首次 put_revision 补建 revision 0（存量建档）
        snap = json.dumps({"asset_id": "char_old", "name": "老人"})
        s.put_revision("char_old", snap, None, "首次修订", "test")
        revs = s.list_revisions("char_old")
        assert [r["revision"] for r in revs] == [0, 1]
        assert revs[0]["reason"] == "存量资产建档"
        assert s.current_revision("char_old") == 1
    finally:
        s.close()


# ---------- T006：revise/rollback 业务 ----------

def _revise(store, aid, patch, **kw):
    from orchestrator.revision import revise
    return revise(store, aid, patch, **kw)


def test_revise_merge_patch_and_versions(store):
    """merge patch 深合并 + 升版 + 历史齐全。"""
    r = _revise(store, "char_a",
                {"persona_spec": {"personality": "急躁"}},
                reason="创作调整", author="writer-agent")
    assert r["revision"] == 1
    # 深合并：其他字段保留，目标字段替换
    asset = store.get_asset("char_a")
    assert asset["persona_spec"]["personality"] == "急躁"
    assert asset["persona_spec"]["secret"] == "甲的秘密"
    # None 删键
    _revise(store, "char_a", {"persona_spec": {"speech_style": None}},
            reason="删口吻")
    asset = store.get_asset("char_a")
    assert "speech_style" not in asset["persona_spec"]
    revs = store.list_revisions("char_a")
    assert [x["revision"] for x in revs] == [0, 1, 2]
    assert revs[1]["reason"] == "创作调整" and revs[1]["author"] == "writer-agent"
    assert revs[1]["patch"]  # patch 留痕


def test_revise_optimistic_lock(store):
    from orchestrator.revision import RevisionConflict
    with pytest.raises(RevisionConflict):
        _revise(store, "char_a", {"name": "乙"}, reason="x",
                base_revision=5)


def test_revise_bad_patch(store):
    from orchestrator.revision import RevisionError
    with pytest.raises(RevisionError, match="BadPatch"):
        _revise(store, "char_a", {}, reason="空")
    with pytest.raises(KeyError):
        _revise(store, "ghost", {"name": "x"}, reason="x")


def test_revise_impacted_runs_warning(store):
    """修订被世界 pin 引用的资产 → 响应带 impacted 与 warning。"""
    store.put_world_config("w1", json.dumps({
        "character_ids": ["char_a"], "location_id": "scene_hall",
        "revisions": {"char_a": 0, "scene_hall": 0}}))
    store.create_run("r1", "w1")
    r = _revise(store, "char_a", {"name": "甲某"}, reason="改名")
    assert r["impacted"] and r["impacted"][0]["world_id"] == "w1"
    assert r["impacted"][0]["pinned_revision"] == 0
    assert "r1" in r["impacted"][0]["run_ids"]
    assert r["warning"]


def test_rollback_restores_and_marks_stale(store):
    _revise(store, "char_a", {"name": "甲某"}, reason="改名")
    _revise(store, "char_a", {"name": "甲某某"}, reason="再改")
    store.put_world_config("w1", json.dumps({
        "character_ids": ["char_a"], "location_id": "scene_hall",
        "revisions": {"char_a": 2, "scene_hall": 0}}))
    from orchestrator.revision import rollback
    r = rollback(store, "char_a", 0)
    assert r["current_revision"] == 0
    assert store.get_asset("char_a")["name"] == "甲"  # 回填 rev0 快照
    assert "w1" in r["stale_worlds"]  # w1 冻结的是 r2，高于回滚目标
    assert len(store.list_revisions("char_a")) == 3  # 历史不删


def test_rollback_not_found(store):
    from orchestrator.revision import RevisionNotFound
    with pytest.raises(RevisionNotFound):
        from orchestrator.revision import rollback
        rollback(store, "char_a", 99)


def test_pollution_guard_three_frozen_faces(store):
    """FR-009：修订/回滚后原料表、事件表、他世界 config 逐字节不变。"""
    store.put_world_config("w1", json.dumps({
        "character_ids": ["char_a"], "location_id": "scene_hall",
        "revisions": {"char_a": 0, "scene_hall": 0}}))
    store.create_run("r1", "w1")
    store.put_event({
        "event_id": "e0001", "run_id": "r1", "tick": 0, "seq": 0,
        "type": "scene_change", "characters": ["char_a"],
        "location": "scene_hall", "content": "开场", "emotion": "",
        "cause_refs": [],
        "shot_hint": {"camera": "wide", "duration_s": 3.0},
        "created_at": "2026-10-21T00:00:00+00:00",
    })
    store.put_material("char_a", "史料", "test", "正文")
    before = (store.get_materials("char_a"), store.export_events("r1"),
              store.get_world_config("w1"))

    _revise(store, "char_a", {"name": "甲某"}, reason="改")
    from orchestrator.revision import rollback
    rollback(store, "char_a", 0)

    after = (store.get_materials("char_a"), store.export_events("r1"),
             store.get_world_config("w1"))
    assert before == after
