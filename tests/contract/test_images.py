"""013 离线测试：参考图生成（mock provider 假字节，零外部调用）。

覆盖：存储原语（T004）/ 生成全链与原子性（T005）/ 提示词覆盖（T008）。
"""
import json
from pathlib import Path

import pytest

from db.init_db import init as init_db
from orchestrator.store import Store

# 最小合法 PNG 头（89 50 4E 47...）+ 填充，足以断言落盘与哈希
FAKE_PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32
FAKE_PNG_B = bytes.fromhex("89504e470d0a1a0a") + b"\x01" * 32

CHAR = {
    "asset_id": "char_a", "type": "character", "name": "甲",
    "appearance": {"visual_prompt": "Song dynasty informer, hemp robe"},
    "persona_spec": {"age": 30, "occupation": "旅人", "personality": "沉稳",
                     "beliefs": "各扫门前雪", "speech_style": "简短",
                     "secret": "甲的秘密"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}
SCENE = {
    "asset_id": "scene_x", "type": "scene", "name": "酒楼",
    "appearance": {"visual_prompt": "tavern by river"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}


class MockImageProvider:
    """假图源：记录入参，返回固定假字节。"""

    name = "mock/image"

    def __init__(self, payloads=None, fail_with=None):
        self.calls = []
        self._payloads = payloads or [FAKE_PNG]
        self._fail = fail_with

    def generate(self, prompt, n, aspect_ratio,
                 subject_reference=None, seed=None):
        self.calls.append({"prompt": prompt, "n": n,
                           "aspect_ratio": aspect_ratio})
        if self._fail:
            raise self._fail
        return (self._payloads * n)[:n]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # images/ 落临时目录
    db = tmp_path / "t.db"
    init_db(db)
    s = Store(db)
    s.put_asset(CHAR)
    s.put_asset(SCENE)
    yield s
    s.close()


# ---------- T004：存储原语 ----------

def test_image_generation_store(store):
    rid = store.put_image_generation("char_a", "p", 1, "2:3",
                                     ["images/char_a/x.png"], ["abc"],
                                     "mock/image", 1)
    assert rid == 1
    rows = store.list_image_generations("char_a")
    assert rows[0]["paths"] == ["images/char_a/x.png"]
    assert rows[0]["sha256"] == ["abc"]
    assert store.list_image_generations("ghost") == []


# ---------- T005：生成全链（mock provider） ----------

def test_generate_full_chain(store):
    from orchestrator.images import generate_reference_images

    provider = MockImageProvider()
    r = generate_reference_images(store, "char_a", provider=provider)
    # provider 收到 visual_prompt 与竖版默认
    assert provider.calls[0]["prompt"] == "Song dynasty informer, hemp robe"
    assert provider.calls[0]["aspect_ratio"] == "2:3"
    # 落盘 + 相对路径登记
    path = r["paths"][0]
    assert path.startswith("images/char_a/")
    assert Path(path).read_bytes() == FAKE_PNG
    asset = store.get_asset("char_a")
    assert asset["reference_images"] == [path]      # 由 image_generations 派生
    # A1：出图不升修订、不改 payload
    assert store.current_revision("char_a") == 0
    assert r["revision"] == 0
    raw = json.loads(store.get_revision("char_a", 0)["payload"])
    assert "reference_images" not in raw
    # 生成记录
    rec = store.list_image_generations("char_a")[0]
    assert rec["prompt"] == "Song dynasty informer, hemp robe"
    assert rec["provider"] == "mock/image"
    assert rec["asset_revision"] == 0
    import hashlib
    assert rec["sha256"][0] == hashlib.sha256(FAKE_PNG).hexdigest()


def test_generate_scene_default_landscape(store):
    from orchestrator.images import generate_reference_images
    provider = MockImageProvider()
    r = generate_reference_images(store, "scene_x", provider=provider)
    assert provider.calls[0]["aspect_ratio"] == "16:9"
    # 显式优先
    generate_reference_images(store, "scene_x", aspect_ratio="1:1",
                              provider=provider)
    assert provider.calls[1]["aspect_ratio"] == "1:1"


def test_generate_bad_prompt(store):
    from orchestrator.images import ImageGenError, generate_reference_images
    store.put_asset(dict(SCENE, asset_id="scene_nop",
                         name="无图场景",
                         appearance={"visual_prompt": "  "}))
    with pytest.raises(ImageGenError, match="BadPrompt"):
        generate_reference_images(store, "scene_nop",
                                  provider=MockImageProvider())


def test_generate_failure_atomic(store, tmp_path):
    from orchestrator.images import ImageGenError, generate_reference_images
    provider = MockImageProvider(fail_with=ImageGenError("429 限流"))
    with pytest.raises(ImageGenError, match="429"):
        generate_reference_images(store, "char_a", provider=provider)
    # 零文件零字段零记录
    assert not (tmp_path / "images").exists()
    assert "reference_images" not in store.get_asset("char_a")
    assert store.list_image_generations("char_a") == []
    assert store.current_revision("char_a") == 0


def test_generate_dedup_same_content(store):
    """同内容重复生成 → 同文件名，不覆盖不重复登记路径。"""
    from orchestrator.images import generate_reference_images
    provider = MockImageProvider()
    r1 = generate_reference_images(store, "char_a", provider=provider)
    r2 = generate_reference_images(store, "char_a", provider=provider)
    assert r1["paths"] == r2["paths"]
    assert len(store.get_asset("char_a")["reference_images"]) == 1


def test_generate_multiple(store):
    from orchestrator.images import generate_reference_images
    provider = MockImageProvider(payloads=[FAKE_PNG, FAKE_PNG_B])
    r = generate_reference_images(store, "char_a", n=2, provider=provider)
    assert len(r["paths"]) == 2
    assert len(set(r["paths"])) == 2  # 不同内容不同文件
    assert len(store.get_asset("char_a")["reference_images"]) == 2


# ---------- T008：提示词覆盖 ----------

def test_prompt_override_traced(store):
    from orchestrator.images import generate_reference_images
    provider = MockImageProvider()
    r = generate_reference_images(store, "char_a",
                                  prompt_override="加强：眼神更阴鸷",
                                  provider=provider)
    assert provider.calls[0]["prompt"] == "加强：眼神更阴鸷"
    assert store.list_image_generations("char_a")[0]["prompt"] == \
        "加强：眼神更阴鸷"


def test_minimax_missing_key(monkeypatch):
    """SC-005：缺密钥时报错消息指明键名。"""
    from orchestrator.images import ImageGenError, MinimaxImageProvider
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(ImageGenError, match="MINIMAX_API_KEY"):
        MinimaxImageProvider().generate("p", 1, "2:3")
