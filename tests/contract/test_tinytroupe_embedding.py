"""003 离线测试：嵌入子类行为 / 预检降级判定 / 配置可移植。

全程离线：嵌入调用在 llama_index.embeddings.openai.base 的 get_embedding(s) 接缝
mock，预检在 httpx 模块属性上 mock，不发起任何真实网络请求。
"""
import httpx
import pytest
from types import SimpleNamespace

import llama_index.embeddings.openai.base as openai_emb_base
from llama_index.core import Settings

from orchestrator.embedding import (
    DEFAULT_EMBEDDING_MODEL,
    DOC_PREFIX,
    EMBEDDING_DIM,
    QUERY_PREFIX,
    build_embedding_model,
    embedding_config,
)
from orchestrator.persona_tinytroupe import TinyTroupeBackend

CFG = {
    "api_base": "http://embedding.invalid/v1",
    "model": "eg2-text-270m.litertlm",
    "timeout_s": 10.0,
    "max_chars": 2000,
}


@pytest.fixture()
def emb():
    return build_embedding_model(CFG)


@pytest.fixture()
def captured(monkeypatch):
    """记录 get_embedding(s) 调用；fail_with 非 None 时抛该异常。"""
    calls = []
    state = {"fail_with": None}

    def fake_get_embedding(client, text, engine, **kwargs):
        calls.append(("single", text, engine))
        if state["fail_with"]:
            raise state["fail_with"]
        return [1.0] * EMBEDDING_DIM

    def fake_get_embeddings(client, list_of_text, engine, **kwargs):
        calls.append(("batch", list(list_of_text), engine))
        if state["fail_with"]:
            raise state["fail_with"]
        return [[1.0] * EMBEDDING_DIM for _ in list_of_text]

    monkeypatch.setattr(openai_emb_base, "get_embedding", fake_get_embedding)
    monkeypatch.setattr(openai_emb_base, "get_embeddings", fake_get_embeddings)
    return SimpleNamespace(calls=calls, state=state)


# ---------- T004：子类行为 ----------

def test_text_embedding_has_doc_prefix(emb, captured):
    vec = emb.get_text_embedding("你好")
    assert vec == [1.0] * EMBEDDING_DIM
    kind, text, engine = captured.calls[0]
    assert text == DOC_PREFIX + "你好"
    assert engine == CFG["model"]


def test_query_embedding_has_query_prefix(emb, captured):
    emb.get_query_embedding("找回忆")
    kind, text, engine = captured.calls[0]
    assert text == QUERY_PREFIX + "找回忆"


def test_empty_text_skips_call_returns_zero(emb, captured):
    assert emb.get_text_embedding("   ") == [0.0] * EMBEDDING_DIM
    assert captured.calls == []


def test_long_text_truncated(emb, captured):
    emb.get_text_embedding("字" * 5000)
    _, text, _ = captured.calls[0]
    assert len(text) == len(DOC_PREFIX) + CFG["max_chars"]


def test_failure_returns_zero_without_raising(emb, captured):
    captured.state["fail_with"] = RuntimeError("服务宕机")
    assert emb.get_text_embedding("你好") == [0.0] * EMBEDDING_DIM
    assert emb.get_query_embedding("回忆") == [0.0] * EMBEDDING_DIM


def test_batch_embeddings_prefix_and_zero_fill(emb, captured):
    vecs = emb.get_text_embedding_batch(["甲", "", "乙"], show_progress=False)
    kind, texts, _ = captured.calls[0]
    assert texts == [DOC_PREFIX + "甲", DOC_PREFIX + "乙"]
    assert vecs[0] == [1.0] * EMBEDDING_DIM
    assert vecs[1] == [0.0] * EMBEDDING_DIM
    assert vecs[2] == [1.0] * EMBEDDING_DIM


# ---------- T002/T011：配置读取与可移植 ----------

def test_config_none_without_env(monkeypatch):
    monkeypatch.delenv("EMBEDDING_API_BASE", raising=False)
    assert embedding_config() is None


def test_config_reads_env_with_defaults(monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://x.invalid/v1/")
    for var in ("EMBEDDING_MODEL", "EMBEDDING_TIMEOUT_S", "EMBEDDING_MAX_CHARS"):
        monkeypatch.delenv(var, raising=False)
    cfg = embedding_config()
    assert cfg["api_base"] == "http://x.invalid/v1"
    assert cfg["model"] == DEFAULT_EMBEDDING_MODEL
    assert cfg["timeout_s"] == 10.0
    assert cfg["max_chars"] == 2000


def test_model_name_bypasses_whitelist(emb):
    assert emb.model_name == CFG["model"]


# ---------- T005/T008：预检与降级接线 ----------

@pytest.fixture()
def real_env(monkeypatch):
    """真后端构造环境：LLM 变量 + 嵌入变量；httpx 与 Settings 均可控。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.invalid")
    monkeypatch.setenv("EMBEDDING_API_BASE", CFG["api_base"])
    monkeypatch.setenv("EMBEDDING_MODEL", CFG["model"])
    saved = Settings.embed_model
    yield
    Settings.embed_model = saved


def _mock_httpx_ok(monkeypatch, seen):
    class Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def fake_get(url, timeout=None, **kw):
        seen.append(("GET", url))
        return Resp({"data": [{"id": CFG["model"]}]})

    def fake_post(url, json=None, timeout=None, **kw):
        seen.append(("POST", url, json))
        return Resp({"data": [{"embedding": [0.5] * EMBEDDING_DIM}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)


def test_real_mode_when_preflight_passes(real_env, monkeypatch):
    seen = []
    _mock_httpx_ok(monkeypatch, seen)
    b = TinyTroupeBackend()
    assert b.semantic_mode == "real"
    assert seen[0] == ("GET", f"{CFG['api_base']}/models")
    assert isinstance(Settings.embed_model, type(Settings.embed_model))
    assert Settings.embed_model.api_base == CFG["api_base"]
    assert Settings.embed_model.model_name == CFG["model"]


def test_degraded_when_env_missing(real_env, monkeypatch):
    monkeypatch.delenv("EMBEDDING_API_BASE")
    def boom(*a, **kw):
        raise AssertionError("未配置时不应发起网络调用")
    monkeypatch.setattr(httpx, "get", boom)
    b = TinyTroupeBackend()
    assert b.semantic_mode.startswith("degraded: 未设置")


def test_degraded_when_service_unreachable(real_env, monkeypatch):
    def boom(*a, **kw):
        raise httpx.ConnectError("connection refused")
    monkeypatch.setattr(httpx, "get", boom)
    b = TinyTroupeBackend()
    assert b.semantic_mode.startswith("degraded: 嵌入服务预检失败")


def test_degraded_when_model_not_listed(real_env, monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"data": [{"id": "other-model"}]}
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: Resp())
    b = TinyTroupeBackend()
    assert "不在服务模型列表" in b.semantic_mode


def test_degraded_memory_injected_only_when_degraded(real_env, monkeypatch):
    from tinytroupe.agent.memory import SemanticMemory

    seen = []
    _mock_httpx_ok(monkeypatch, seen)
    real_backend = TinyTroupeBackend()
    person = real_backend._get_person("char_x", {"name": "甲"})
    assert type(person.semantic_memory) is SemanticMemory

    monkeypatch.delenv("EMBEDDING_API_BASE")
    degraded_backend = TinyTroupeBackend()
    person2 = degraded_backend._get_person("char_y", {"name": "乙"})
    assert type(person2.semantic_memory) is not SemanticMemory
    assert person2.semantic_memory.retrieve_relevant("任意") == []


# ---------- T011：无硬编码地址 ----------

def test_no_hardcoded_embedding_address():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    targets = [root / "orchestrator", root / "scripts" / "run_real_chain.py",
               root / "scripts" / "probe_embedding_service.py"]
    offenders = []
    for target in targets:
        files = target.rglob("*.py") if target.is_dir() else [target]
        for f in files:
            text = f.read_text(encoding="utf-8")
            if "9379" in text or "127.0.0.1" in text:
                offenders.append(str(f))
    assert offenders == [], f"硬编码嵌入服务地址: {offenders}"
