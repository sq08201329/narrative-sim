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
