"""011 US3 离线测试：素材移交包（handoff/ 目录，零外部调用）。

覆盖：目录布局 / manifest 自描述（sha256、counts、revision_pins、secrecy）/
空世界 / 覆盖保护 / secret 密级标注（T010）。
"""
import hashlib
import json

import pytest

from db.init_db import init as init_db
from orchestrator.store import Store


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


SCENE = {
    "asset_id": "scene_hall", "type": "scene", "name": "临河酒楼",
    "appearance": {"visual_prompt": "tavern", "description": "临河"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}
CHAR = {
    "asset_id": "char_a", "type": "character", "name": "甲",
    "appearance": {"visual_prompt": "look"},
    "persona_spec": {"age": 30, "occupation": "旅人", "personality": "沉稳",
                     "beliefs": "各扫门前雪", "speech_style": "简短",
                     "secret": "甲的秘密"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    s = Store(db)
    s.put_asset(SCENE)
    s.put_asset(CHAR)
    yield s
    s.close()


def _full_world(store):
    """建世界 + run + 事件 + 裁决 + 原料。"""
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
    store.put_dm_call("r1", 1, "act", "char_a", "{}", "hint", "叙事",
                      '[{"operator": "set"}]', 10, 5, 0.5, False)
    store.finish_run("r1", "done")
    store.put_world_state("w1", 1, json.dumps({"tick": 1, "entities": []}))
    store.put_material("char_a", "皇城司侦缉手段", "test-retriever", "原料正文")


def test_handoff_layout_and_manifest(store, tmp_path):
    _full_world(store)
    from orchestrator.handoff import export_handoff
    out = export_handoff(store, "w1", str(tmp_path / "handoff"), run_id="r1")

    d = tmp_path / "handoff" / "w1"
    assert out["dir"] == str(d)
    # 目录布局
    assert (d / "manifest.json").exists()
    assert (d / "assets" / "char_a.json").exists()
    assert (d / "assets" / "scene_hall.json").exists()
    assert (d / "events.jsonl").exists()
    assert (d / "world.json").exists()
    assert (d / "dm_calls.json").exists()
    assert (d / "materials" / "char_a.md").exists()
    assert (d / "sources.md").exists()

    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "narrative-sim-handoff/1"
    assert manifest["world_id"] == "w1" and manifest["run_id"] == "r1"
    assert manifest["revision_pins"] == {"char_a": 0, "scene_hall": 0}
    assert manifest["counts"] == {"assets": 2, "events": 1, "dm_calls": 1,
                                  "materials": 1, "images": 0}
    assert "secret" in manifest["secrecy"]
    # sha256 自描述：manifest 每项与文件实算一致
    for item in manifest["items"]:
        f = d / item["path"]
        assert f.exists(), item["path"]
        assert _sha(f) == item["sha256"]
        assert f.stat().st_size == item["bytes"]

    # 资产文件含 secret 且带密级标注
    asset = json.loads((d / "assets" / "char_a.json").read_text("utf-8"))
    assert asset["persona_spec"]["secret"] == "甲的秘密"
    assert "secrecy" in asset
    # 事件与台账口径
    lines = (d / "events.jsonl").read_text("utf-8").strip().split("\n")
    assert json.loads(lines[0])["type"] == "scene_change"
    calls = json.loads((d / "dm_calls.json").read_text("utf-8"))
    assert calls[0]["tokens_in"] == 10
    # 原料 md 含正文与来源；sources.md 汇总
    md = (d / "materials" / "char_a.md").read_text("utf-8")
    assert "皇城司侦缉手段" in md and "原料正文" in md
    sources = (d / "sources.md").read_text("utf-8")
    assert "test-retriever" in sources


def test_handoff_empty_world(store, tmp_path):
    """空世界（无 run）：events/dm_calls 为空集合，不报错。"""
    store.put_world_config("w_empty", json.dumps({
        "character_ids": ["char_a"], "location_id": "scene_hall",
        "revisions": {"char_a": 0, "scene_hall": 0}}))
    from orchestrator.handoff import export_handoff
    out = export_handoff(store, "w_empty", str(tmp_path / "handoff"))
    d = tmp_path / "handoff" / "w_empty"
    assert json.loads((d / "events.jsonl").read_text("utf-8") or "[]") == [] \
        or (d / "events.jsonl").read_text("utf-8") == ""
    assert json.loads((d / "dm_calls.json").read_text("utf-8")) == []
    assert out["counts"]["events"] == 0


def test_handoff_overwrite_guard(store, tmp_path):
    _full_world(store)
    from orchestrator.handoff import HandoffExists, export_handoff
    export_handoff(store, "w1", str(tmp_path / "handoff"), run_id="r1")
    with pytest.raises(HandoffExists):
        export_handoff(store, "w1", str(tmp_path / "handoff"), run_id="r1")
    # 显式覆盖
    out = export_handoff(store, "w1", str(tmp_path / "handoff"),
                         run_id="r1", overwrite=True)
    assert out["counts"]["events"] == 1


def test_handoff_world_not_found(store, tmp_path):
    from orchestrator.handoff import export_handoff
    with pytest.raises(KeyError, match="w_ghost"):
        export_handoff(store, "w_ghost", str(tmp_path / "handoff"))


# ---------- 013 US3：移交包带图 ----------

def test_handoff_with_images(store, tmp_path):
    """显式 include_images=True 才带图；默认不带（自产图为内部草稿）。"""
    _full_world(store)
    # 给 char_a 造一张已登记参考图（直接放文件 + 更新资产，走 put_asset）
    img_dir = tmp_path / "img_src"
    img_dir.mkdir()
    fake = img_dir / "ref.png"
    fake.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    # A1：参考图经 image_generations 登记（reference_images 由它派生）
    store.put_image_generation("char_a", "p", 1, "2:3", [str(fake)],
                               [_sha(fake)], "test",
                               store.current_revision("char_a"))

    from orchestrator.handoff import export_handoff
    # 默认：不带图
    out = export_handoff(store, "w1", str(tmp_path / "h_default"),
                         run_id="r1")
    assert out["counts"]["images"] == 0
    assert not (tmp_path / "h_default" / "w1" / "images").exists()
    # 显式带图
    out = export_handoff(store, "w1", str(tmp_path / "handoff"),
                         run_id="r1", include_images=True)
    d = tmp_path / "handoff" / "w1"
    copied = d / "images" / "char_a" / "ref.png"
    assert copied.exists() and copied.read_bytes() == fake.read_bytes()
    assert out["counts"]["images"] == 1
    manifest = json.loads((d / "manifest.json").read_text("utf-8"))
    img_items = [i for i in manifest["items"] if i["kind"] == "image"]
    assert len(img_items) == 1
    assert _sha(copied) == img_items[0]["sha256"]


def test_handoff_without_images(store, tmp_path):
    """无图世界：images 计数为 0，不报错。"""
    _full_world(store)
    from orchestrator.handoff import export_handoff
    out = export_handoff(store, "w1", str(tmp_path / "handoff"), run_id="r1")
    assert out["counts"]["images"] == 0
