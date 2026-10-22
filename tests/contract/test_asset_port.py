"""asset_port 契约测试：导出 / 导入 / 核对（真实 SQLite tmp 库，零外部调用）。

覆盖：往返一致 / 幂等 / 冲突不覆盖 / dst 领先 / 允许补齐 / 原料增量 /
坏文件 / 手写资产 / 只碰三张表 / put_asset+put_revision 原行为不变。
"""
import json

import pytest

from db.init_db import init as init_db
from orchestrator.asset_port import (
    AssetPortError,
    BundleCorrupt,
    DstAhead,
    DstBehind,
    ManualAssetRejected,
    RevisionConflict,
    export_asset,
    import_bundle,
    verify_bundle,
)
from orchestrator.store import Store

ASSET_ID = "char_x"
MAT_A = "原料甲：南宋临安街市上的逻卒，凭腰牌行缉事之职。" * 3
MAT_B = "原料乙：皇城司不隶台察，逻卒十日不探到事即决杖。"


def _char(name="甲", retriever="gptr-mcp(deepseek-search)",
          personality="沉稳") -> dict:
    return {
        "asset_id": ASSET_ID,
        "type": "character",
        "name": name,
        "appearance": {"visual_prompt": f"{name} look"},
        "persona_spec": {"age": 30, "occupation": "逻卒",
                         "personality": personality, "beliefs": "听命",
                         "speech_style": "简短", "secret": "密"},
        "provenance": {"researched_at": "2026-10-20T00:00:00+00:00",
                       "retriever": retriever, "model": "deepseek-flash",
                       "confidence": 0.9},
    }


def _open(path) -> Store:
    init_db(path)
    return Store(path)


def _export(tmp_path, src) -> str:
    path = tmp_path / "bundle.json"
    export_asset(src, ASSET_ID, str(path))
    return str(path)


def _snapshot(store: Store, asset_id: str = ASSET_ID) -> dict:
    return {
        "asset": store.get_asset(asset_id),
        "current_revision": store.current_revision(asset_id),
        "revisions": [dict(r) for r in store.list_revisions(asset_id)],
        "materials": [dict(m) for m in store.get_materials(asset_id)],
    }


def _source(tmp_path) -> Store:
    src = _open(tmp_path / "library.db")
    src.put_asset(_char())                                      # revision 0
    src.put_revision(ASSET_ID,
                     json.dumps(_char(personality="谨慎"), ensure_ascii=False),
                     None, "编辑修订", "editor")                 # revision 1
    src.put_material(ASSET_ID, "南宋临安逻卒", "gptr-mcp", MAT_A)
    src.put_material(ASSET_ID, "南宋街市暗号", "gptr-mcp", MAT_B)
    return src


# ---------- 往返一致 ----------

def test_export_import_roundtrip_identical(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        plan = import_bundle(dst, bundle, backup=False,
                             db_path=str(tmp_path / "project.db"))
        assert plan["action"] == "insert"
        assert plan["revisions_added"] == 2
        assert plan["materials_added"] == 2

        rows = {r["asset_id"]: r for r in dst.list_asset_summaries()}
        assert rows[ASSET_ID]["current_revision"] == \
            src.current_revision(ASSET_ID)
        assert rows[ASSET_ID]["status"] == "draft"

        got = {int(r["revision"]): json.loads(r["payload"])
               for r in dst.list_revisions(ASSET_ID)}
        want = {int(r["revision"]): json.loads(r["payload"])
                for r in src.list_revisions(ASSET_ID)}
        assert got == want                       # 修订号与内容都保号

        assert [m["context"] for m in dst.get_materials(ASSET_ID)] == \
               [m["context"] for m in src.get_materials(ASSET_ID)]
        # 指针不变量
        cur = dst.current_revision(ASSET_ID)
        assert json.loads(dst.get_revision(ASSET_ID, cur)["payload"]) == \
            dst.get_asset(ASSET_ID)
        assert verify_bundle(dst, bundle)["ok"] is True
    finally:
        src.close()
        dst.close()


def test_import_is_idempotent(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        first = import_bundle(dst, bundle, backup=False)
        assert first["action"] == "insert"
        before = _snapshot(dst)

        second = import_bundle(dst, bundle, backup=False)
        assert second["action"] == "identical"
        assert second["revisions_added"] == 0
        assert second["materials_added"] == 0
        assert _snapshot(dst) == before
        assert verify_bundle(dst, bundle)["ok"] is True
    finally:
        src.close()
        dst.close()


# ---------- 冲突：不覆盖 ----------

def test_conflict_same_revision_different_content(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        dst.put_asset(_char())                                  # rev0 相同
        dst.put_revision(ASSET_ID,
                         json.dumps(_char(personality="完全不同的另一版"),
                                    ensure_ascii=False),
                         None, "分歧版", "someone")             # rev1 不同
        before = _snapshot(dst)
        with pytest.raises(RevisionConflict, match="同号不同内容"):
            import_bundle(dst, bundle, backup=False)
        assert _snapshot(dst) == before
    finally:
        src.close()
        dst.close()


def test_dst_ahead_rejected(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        dst.put_asset(_char())
        dst.put_revision(ASSET_ID,
                         json.dumps(_char(personality="谨慎"),
                                    ensure_ascii=False), None, "对齐", "x")
        dst.put_revision(ASSET_ID,
                         json.dumps(_char(personality="又改一版"),
                                    ensure_ascii=False), None, "本地新修", "x")
        before = _snapshot(dst)
        with pytest.raises(DstAhead, match="目标库领先"):
            import_bundle(dst, bundle, backup=False)
        assert _snapshot(dst) == before
    finally:
        src.close()
        dst.close()


def test_dst_behind_requires_allow_extend(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        dst.put_asset(_char())                                  # 只到 rev0
        with pytest.raises(DstBehind, match="目标库落后"):
            import_bundle(dst, bundle, backup=False)
        assert dst.current_revision(ASSET_ID) == 0

        plan = import_bundle(dst, bundle, allow_extend=True, backup=False)
        assert plan["action"] == "extend"
        assert plan["revisions_added"] == 1
        assert dst.current_revision(ASSET_ID) == 1
        assert verify_bundle(dst, bundle)["ok"] is True
    finally:
        src.close()
        dst.close()


# ---------- 原料 ----------

def test_materials_only_add_missing(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        dst.put_asset(_char())
        dst.put_material(ASSET_ID, "南宋临安逻卒", "gptr-mcp", MAT_A)
        plan = import_bundle(dst, bundle, allow_extend=True, backup=False)
        assert plan["materials_added"] == 1
        contexts = [m["context"] for m in dst.get_materials(ASSET_ID)]
        assert contexts.count(MAT_A) == 1        # 不重复
        assert MAT_B in contexts                 # 原样补入，未截断
        verify = verify_bundle(dst, bundle)
        assert verify["ok"] is True
        assert verify["materials"]["missing"] == 0
    finally:
        src.close()
        dst.close()


def test_verify_extra_content_is_not_failure(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        import_bundle(dst, bundle, backup=False)
        dst.put_material(ASSET_ID, "项目库本地补料", "manual", "本地补的一条")
        result = verify_bundle(dst, bundle)
        assert result["ok"] is True
        assert result["materials"]["extra"] == 1
    finally:
        src.close()
        dst.close()


# ---------- 坏文件 / 手写资产 ----------

def test_corrupt_bundle_detected(tmp_path):
    src = _source(tmp_path)
    bundle_path = _export(tmp_path, src)
    dst = _open(tmp_path / "project.db")
    try:
        data = json.loads(open(bundle_path, encoding="utf-8").read())
        data["asset"]["payload_sha256"] = "0" * 64
        open(bundle_path, "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False))
        with pytest.raises(BundleCorrupt, match="payload_sha256"):
            import_bundle(dst, bundle_path, backup=False)
        with pytest.raises(BundleCorrupt):
            verify_bundle(dst, bundle_path)
    finally:
        src.close()
        dst.close()


def test_bundle_bad_asset_type_is_corrupt(tmp_path):
    src = _source(tmp_path)
    bundle_path = _export(tmp_path, src)
    dst = _open(tmp_path / "project.db")
    try:
        data = json.loads(open(bundle_path, encoding="utf-8").read())
        data["asset"]["type"] = "monster"
        data["fingerprint"]["bundle_sha256"] = "x"
        open(bundle_path, "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False))
        with pytest.raises(BundleCorrupt):
            import_bundle(dst, bundle_path, backup=False)
    finally:
        src.close()
        dst.close()


def test_manual_asset_rejected_by_default(tmp_path):
    src = _open(tmp_path / "library.db")
    src.put_asset(_char(retriever="manual"))
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        summary = json.loads(open(bundle, encoding="utf-8").read())
        assert summary["provenance"] == "manual"
        with pytest.raises(ManualAssetRejected, match="manual"):
            import_bundle(dst, bundle, backup=False)
        assert not dst.list_asset_summaries()
        plan = import_bundle(dst, bundle, allow_manual=True, backup=False)
        assert plan["action"] == "insert"
        assert plan["provenance"] == "manual"
    finally:
        src.close()
        dst.close()


# ---------- 边界与不变量 ----------

def test_export_missing_asset_raises(tmp_path):
    src = _open(tmp_path / "library.db")
    try:
        with pytest.raises(AssetPortError, match="资产不存在"):
            export_asset(src, "char_ghost", str(tmp_path / "x.json"))
    finally:
        src.close()


def _non_port_counts(store: Store) -> dict:
    """四张「禁碰」表的行数，全部经 Store 既有读方法取（不直连 sqlite3）。"""
    return {
        "worlds": len(store.list_world_configs()),
        "runs": len(store.list_runs("w1")),
        "events": len(store.export_events("r1")),
        "dm_calls": len(store.list_dm_calls("r1")),
    }


def test_import_touches_only_three_tables(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        # 用既有 API 造四张「禁碰」表的数据（保持存储唯一入口：不直连 sqlite3）
        dst.put_world_config("w1", "")
        dst.create_run("r1", "w1")
        dst.put_event({
            "event_id": "e0001", "run_id": "r1", "tick": 0, "seq": 0,
            "type": "scene_change", "characters": ["char_x"],
            "location": "scene_y", "content": "场景",
            "cause_refs": [],
            "shot_hint": {"camera": "wide", "duration_s": 3.0},
            "created_at": "2026-10-22T00:00:00+00:00",
        })
        dst.put_dm_call("r1", 0, "act", "char_x", "{}", "", "", "[]",
                        0, 0, 0.0, False)

        before = _non_port_counts(dst)
        import_bundle(dst, bundle, backup=False)
        assert _non_port_counts(dst) == before
        assert len(dst.list_asset_summaries()) == 1
    finally:
        src.close()
        dst.close()


def test_put_asset_and_put_revision_semantics_unchanged(tmp_path):
    """导入专用方法不得改变原有入库/修订语义（主路径回归锚点）。"""
    store = _open(tmp_path / "regress.db")
    try:
        store.put_asset(_char())                     # 首建：自动 revision 0
        revs = store.list_revisions(ASSET_ID)
        assert len(revs) == 1 and revs[0]["revision"] == 0
        assert revs[0]["author"] == "gptr-mcp(deepseek-search)"
        assert revs[0]["reason"] == "调研原版"

        store.put_asset(_char(personality="急躁"))   # 内容变：自动升版
        revs = store.list_revisions(ASSET_ID)
        assert len(revs) == 2 and store.current_revision(ASSET_ID) == 1
        assert revs[1]["author"] == "system:put_asset"

        store.put_asset(_char(personality="急躁"))   # 内容不变：不升版
        assert len(store.list_revisions(ASSET_ID)) == 2

        store.put_revision(ASSET_ID,
                           json.dumps(_char(personality="更急躁"),
                                      ensure_ascii=False),
                           None, "手动修订", "editor")
        assert store.current_revision(ASSET_ID) == 2
        assert store.list_revisions(ASSET_ID)[2]["author"] == "editor"
    finally:
        store.close()
