"""014 契约测试：图生图（subject_reference）与 seed 复现。

覆盖：不传新参 payload 逐键回归 / 魔数判型 / data URL 透传 /
payload 透传 / 错误零计费（spy 证明 generate 未被调用）/ HTTP 状态码可读 /
返回值不回显 data URL / 超时默认 180s。
"""
import base64
import json

import pytest

from db.init_db import init as init_db
from orchestrator.images import (
    ImageGenError,
    MinimaxImageProvider,
    _to_data_url,
    generate_reference_images,
)
from orchestrator.store import Store

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
BASE_KEYS = {"model", "prompt", "aspect_ratio", "n", "response_format"}
DATA_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()

CHAR = {
    "asset_id": "char_a", "type": "character", "name": "甲",
    "appearance": {"visual_prompt": "Song dynasty informer, hemp robe"},
    "persona_spec": {"age": 30, "occupation": "旅人", "personality": "沉稳",
                     "beliefs": "各扫门前雪", "speech_style": "简短",
                     "secret": "甲的密"},
    "provenance": {"researched_at": "t", "retriever": "test", "model": "test",
                   "confidence": 0.5},
}


class Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code = status
        self._body = body
        self.text = text

    def json(self):
        return self._body


def _capture(monkeypatch, status=200):
    seen = {}
    body = {"base_resp": {"status_code": 0},
            "data": {"image_base64": [base64.b64encode(PNG).decode()]}}

    def fake_post(url, headers=None, json=None, timeout=None, **kw):
        seen.update({"url": url, "headers": headers, "json": json,
                     "timeout": timeout})
        if status >= 300:
            return Resp(status, None, "Request Entity Too Large: body too big")
        return Resp(200, body)

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
    return seen


class SpyProvider:
    name = "spy/provider"

    def __init__(self):
        self.calls = []

    def generate(self, prompt, n, aspect_ratio,
                 subject_reference=None, seed=None):
        self.calls.append({"prompt": prompt, "n": n,
                           "aspect_ratio": aspect_ratio,
                           "subject_reference": subject_reference,
                           "seed": seed})
        return [PNG]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # images/ 落临时目录
    db = tmp_path / "t.db"
    init_db(db)
    s = Store(db)
    s.put_asset(CHAR)
    yield s
    s.close()


# ---------- 回归：不传新参时 payload 逐键一致 ----------

def test_payload_key_set_unchanged_without_new_params(monkeypatch):
    seen = _capture(monkeypatch)
    provider = MinimaxImageProvider()
    provider.generate("一个南宋逻卒", 1, "2:3")
    assert set(seen["json"].keys()) == BASE_KEYS        # 完整键集合，不抽查
    assert seen["json"]["model"] == "image-01"
    assert seen["json"]["response_format"] == "base64"
    assert seen["json"]["prompt"] == "一个南宋逻卒"
    assert seen["json"]["aspect_ratio"] == "2:3"
    assert seen["json"]["n"] == 1


def test_timeout_default_is_180(monkeypatch):
    seen = _capture(monkeypatch)
    MinimaxImageProvider().generate("p", 1, "2:3")
    assert seen["timeout"] == 180.0


# ---------- 参考图：魔数判型 / 透传 / 校验 ----------

def test_magic_bytes_win_over_extension(tmp_path):
    # 内容是 PNG，文件名却叫 .txt
    f = tmp_path / "renamed.txt"
    f.write_bytes(PNG)
    url = _to_data_url(str(f))
    assert url.startswith("data:image/png;base64,")


def test_jpeg_magic_with_png_suffix(tmp_path):
    f = tmp_path / "actually_png_name.png"
    f.write_bytes(JPEG)
    assert _to_data_url(str(f)).startswith("data:image/jpeg;base64,")


def test_data_url_passthrough():
    assert _to_data_url(DATA_URL) == DATA_URL


def test_missing_reference_error(tmp_path):
    with pytest.raises(ImageGenError, match="不存在"):
        _to_data_url(str(tmp_path / "nope.jpg"))


def test_bad_format_error(tmp_path):
    f = tmp_path / "not_image.txt"
    f.write_bytes(b"definitely not an image")
    with pytest.raises(ImageGenError, match="格式不支持"):
        _to_data_url(str(f))


def test_too_large_error(tmp_path):
    f = tmp_path / "big.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024))
    with pytest.raises(ImageGenError, match="10MB"):
        _to_data_url(str(f))


def test_payload_carries_subject_reference_and_seed(monkeypatch):
    seen = _capture(monkeypatch)
    MinimaxImageProvider().generate("p", 2, "2:3",
                                    subject_reference=DATA_URL, seed=42)
    assert seen["json"]["subject_reference"] == [
        {"type": "character", "image_file": DATA_URL}]
    assert seen["json"]["seed"] == 42


def test_seed_string_coerced_to_int(monkeypatch):
    seen = _capture(monkeypatch)
    MinimaxImageProvider().generate("p", 1, "2:3", seed="42")
    assert seen["json"]["seed"] == 42 and isinstance(seen["json"]["seed"], int)


# ---------- 错误零计费：非法参考图不调用 provider ----------

@pytest.mark.parametrize("case", ["missing", "bad_format", "too_large"])
def test_invalid_reference_never_calls_provider(store, tmp_path, case):
    spy = SpyProvider()
    if case == "missing":
        ref = str(tmp_path / "nope.jpg")
    elif case == "bad_format":
        f = tmp_path / "x.txt"
        f.write_bytes(b"not an image")
        ref = str(f)
    else:
        f = tmp_path / "big.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * (10 * 1024 * 1024))
        ref = str(f)
    with pytest.raises(ImageGenError):
        generate_reference_images(store, "char_a", provider=spy,
                                  subject_reference=ref)
    assert spy.calls == []          # 硬证据：provider 一次都没被调用


# ---------- HTTP 状态码与不回显 ----------

def test_http_413_reported_without_body_echo(monkeypatch):
    _capture(monkeypatch, status=413)
    with pytest.raises(ImageGenError) as ei:
        MinimaxImageProvider().generate(
            "p", 1, "2:3", subject_reference=DATA_URL)
    msg = str(ei.value)
    assert "HTTP 413" in msg
    assert "Entity Too Large" in msg
    assert "data:image" not in msg          # 不得回显 data URL


def test_result_does_not_echo_data_url(store, tmp_path):
    spy = SpyProvider()
    f = tmp_path / "ref.png"
    f.write_bytes(PNG)
    result = generate_reference_images(store, "char_a", provider=spy,
                                       subject_reference=str(f), seed=7)
    assert result["seed"] == 7
    assert result["used_reference"] is True
    # 传给 provider 的是已转换的 data URL
    assert spy.calls[0]["subject_reference"].startswith("data:image/png;base64,")
    assert spy.calls[0]["seed"] == 7
    # 返回值里不得出现 data URL 全文
    assert "data:image" not in json.dumps(result, ensure_ascii=False)


def test_result_without_reference_marks_false(store):
    spy = SpyProvider()
    result = generate_reference_images(store, "char_a", provider=spy)
    assert result["used_reference"] is False
    assert result["seed"] is None
    assert spy.calls[0]["subject_reference"] is None
