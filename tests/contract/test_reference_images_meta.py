"""A1 + B1 契约测试：reference_images 派生 / 出图不顶修订 / 跨库内容比对。

覆盖：
- A1：reference_images 由 image_generations 派生（稳定排序、去重）；出图不改
  payload、不升修订；revise/rollback/import 不把该字段写回当前 payload。
- B1：bundle 带 content_sha256；目标库修订号更高但内容一致 → identical_content；
  老 bundle 无 content_sha256 → 回退旧口径并告警；verify 把图片差异单列不算失败。
"""
import hashlib
import json
import logging

import pytest

from db.init_db import init as init_db
from orchestrator.asset_port import (
    export_asset,
    import_bundle,
    verify_bundle,
)
from orchestrator.revision import revise, rollback
from orchestrator.store import Store

ASSET_ID = "char_x"
MAT_A = "原料甲：南宋临安街市上的逻卒，凭腰牌行缉事之职。" * 3
MAT_B = "原料乙：皇城司不隶台察，逻卒十日不探到事即决杖。"


def _char(personality="沉稳", retriever="gptr-mcp(deepseek-search)") -> dict:
    return {
        "asset_id": ASSET_ID,
        "type": "character",
        "name": "甲",
        "appearance": {"visual_prompt": "甲 look"},
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


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


# ---------- A1：reference_images 派生 ----------

def test_reference_images_derived_sorted_and_deduped(tmp_path):
    store = _open(tmp_path / "t.db")
    try:
        store.put_asset(_char())
        # 两次登记，路径需按 (created_at, sha) 稳定排序，且重复路径去重
        store.put_image_generation(ASSET_ID, "p1", 2, "2:3",
                                   ["images/char_x/bbbb.png", "images/char_x/aaaa.png"],
                                   ["sha-b", "sha-a"], "mock", 0)
        store.put_image_generation(ASSET_ID, "p2", 1, "2:3",
                                   ["images/char_x/aaaa.png"],
                                   ["sha-a"], "mock", 0)
        imgs = store.reference_images(ASSET_ID)
        assert imgs == ["images/char_x/aaaa.png", "images/char_x/bbbb.png"]
        assert store.get_asset(ASSET_ID)["reference_images"] == imgs
        # payload 里不存该字段
        raw = json.loads(store.get_revision(ASSET_ID, 0)["payload"])
        assert "reference_images" not in raw
    finally:
        store.close()


def test_generate_reference_images_does_not_bump_revision(tmp_path, monkeypatch):
    from orchestrator.images import generate_reference_images

    class FakeProvider:
        name = "mock/image"

        def generate(self, prompt, n, aspect_ratio,
                     subject_reference=None, seed=None):
            return [b"\x89PNG\r\n\x1a\n" + b"\x00" * 8]

    monkeypatch.chdir(tmp_path)  # images/ 落临时目录
    store = _open(tmp_path / "t.db")
    try:
        store.put_asset(_char())
        r = generate_reference_images(store, ASSET_ID, provider=FakeProvider())
        assert r["revision"] == store.current_revision(ASSET_ID) == 0
        assert r["reference_images"] == store.reference_images(ASSET_ID)
        assert len(r["paths"]) == 1 and r["reference_images"] == r["paths"]
        raw = json.loads(store.get_revision(ASSET_ID, 0)["payload"])
        assert "reference_images" not in raw
        assert len(store.list_image_generations(ASSET_ID)) == 1
    finally:
        store.close()


def test_revise_strips_reference_images_and_warns(tmp_path):
    store = _open(tmp_path / "t.db")
    try:
        store.put_asset(_char())
        out = revise(store, ASSET_ID,
                     {"personality": "谨慎", "reference_images": ["x.png"]},
                     "试改图")
        assert out["revision"] == 1
        assert out["warning"] and "reference_images" in out["warning"]
        raw = json.loads(store.get_revision(ASSET_ID, 1)["payload"])
        assert "reference_images" not in raw
        assert "reference_images" not in store.get_asset(ASSET_ID)
    finally:
        store.close()


def test_rollback_strips_reference_images(tmp_path):
    store = _open(tmp_path / "t.db")
    try:
        legacy = dict(_char(), reference_images=["images/char_x/legacy.png"])
        store.put_asset(legacy)                       # rev0 带历史遗留字段
        store.put_revision(ASSET_ID,
                           json.dumps(_char(personality="谨慎"),
                                      ensure_ascii=False),
                           None, "新一版", "editor")   # rev1
        rollback(store, ASSET_ID, 0)
        assert store.current_revision(ASSET_ID) == 0
        hist = json.loads(store.get_revision(ASSET_ID, 0)["payload"])
        assert "reference_images" in hist        # 约束1：历史修订行原样保留
        row = store._conn.execute(
            "SELECT payload FROM assets WHERE asset_id=?", (ASSET_ID,)
        ).fetchone()
        assert "reference_images" not in json.loads(row["payload"])  # 当前 payload 剥离
        assert "reference_images" not in store.get_asset(ASSET_ID)
    finally:
        store.close()


# ---------- B1：跨库内容比对 ----------

def _source(tmp_path) -> Store:
    src = _open(tmp_path / "library.db")
    src.put_asset(_char())
    src.put_revision(ASSET_ID,
                     json.dumps(_char(personality="谨慎"), ensure_ascii=False),
                     None, "编辑修订", "editor")
    src.put_material(ASSET_ID, "南宋临安逻卒", "gptr-mcp", MAT_A)
    src.put_material(ASSET_ID, "南宋街市暗号", "gptr-mcp", MAT_B)
    return src


def test_bundle_carries_content_sha_and_reference_images(tmp_path):
    src = _source(tmp_path)
    try:
        bundle = json.loads(open(_export(tmp_path, src), encoding="utf-8").read())
        asset = bundle["asset"]
        assert "content_sha256" in asset
        assert asset["reference_images"] == []
        for rev in bundle["revisions"]:
            assert "content_sha256" in rev
    finally:
        src.close()


def test_dst_higher_revision_same_content_is_identical_content(tmp_path):
    """项目库修订号被出图顶高、内容一致 → 不拒、不写资产、只补原料。"""
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        dst.put_asset(_char())
        dst.put_revision(ASSET_ID,
                         json.dumps(_char(personality="谨慎"),
                                    ensure_ascii=False), None, "内容版", "x")
        dst.put_revision(ASSET_ID,
                         json.dumps(_char(personality="谨慎"),
                                    ensure_ascii=False), None, "出图副作用", "x")
        current_before = dst.current_revision(ASSET_ID)
        plan = import_bundle(dst, bundle, backup=False)
        assert plan["action"] == "identical_content"
        assert plan["revisions_added"] == 0
        assert dst.current_revision(ASSET_ID) == current_before  # 不被顶回
        result = verify_bundle(dst, bundle)
        assert result["ok"] is True
        assert result["revisions"]["extra"] == [2]
    finally:
        src.close()
        dst.close()


def test_dst_higher_revision_different_content_still_rejected(tmp_path):
    from orchestrator.asset_port import DstAhead

    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        dst.put_asset(_char())
        dst.put_revision(ASSET_ID,
                         json.dumps(_char(personality="谨慎"),
                                    ensure_ascii=False), None, "同内容", "x")
        dst.put_revision(ASSET_ID,
                         json.dumps(_char(personality="完全不同的另一版"),
                                    ensure_ascii=False), None, "真分歧", "x")
        with pytest.raises(DstAhead, match="内容领先"):
            import_bundle(dst, bundle, backup=False)
    finally:
        src.close()
        dst.close()


def test_verify_reference_images_difference_not_failure(tmp_path):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    bundle = _export(tmp_path, src)
    try:
        import_bundle(dst, bundle, backup=False)
        dst.put_image_generation(ASSET_ID, "p", 1, "2:3",
                                 ["images/char_x/only-in-project.png"],
                                 ["sha-x"], "mock",
                                 dst.current_revision(ASSET_ID))
        result = verify_bundle(dst, bundle)
        assert result["ok"] is True
        assert result["images"]["extra"] == [
            "images/char_x/only-in-project.png"]
        assert result["images"]["missing"] == []
    finally:
        src.close()
        dst.close()


def test_import_legacy_bundle_falls_back_with_warning(tmp_path, caplog):
    src = _source(tmp_path)
    dst = _open(tmp_path / "project.db")
    path = _export(tmp_path, src)
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        data["asset"].pop("content_sha256")
        for rev in data["revisions"]:
            rev.pop("content_sha256")
        body = {"format": data["format"], "asset": data["asset"],
                "revisions": data["revisions"],
                "materials": data["materials"],
                "provenance": data["provenance"]}
        data["fingerprint"] = {
            "asset_sha256": data["asset"]["payload_sha256"],
            "revisions_sha256": _sha_text(_canon(data["revisions"])),
            "materials_sha256": _sha_text(_canon(data["materials"])),
            "bundle_sha256": _sha_text(_canon(body)),
        }
        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text(json.dumps(data, ensure_ascii=False),
                               encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="orchestrator.asset_port"):
            plan = import_bundle(dst, str(legacy_path), backup=False)
        assert plan["action"] == "insert"
        assert plan["legacy_bundle"] is True
        assert any("老格式 bundle" in r.message for r in caplog.records)
    finally:
        src.close()
        dst.close()


def test_import_strips_reference_images_from_payload(tmp_path):
    src = _open(tmp_path / "library.db")
    dst = _open(tmp_path / "project.db")
    try:
        legacy = dict(_char(), reference_images=["images/char_x/a.png"])
        src.put_asset(legacy)
        bundle = _export(tmp_path, src)
        data = json.loads(open(bundle, encoding="utf-8").read())
        assert data["asset"]["payload"]["reference_images"] == [
            "images/char_x/a.png"]
        import_bundle(dst, bundle, backup=False)
        raw = json.loads(dst.get_revision(ASSET_ID, 0)["payload"])
        assert "reference_images" not in raw
    finally:
        src.close()
        dst.close()
