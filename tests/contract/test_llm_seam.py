"""LLM 接缝契约：import 安全、缺环境变量时明确报错（宪章原则 VI + 技术栈约束）。

外部服务地址与模型名 MUST 从环境变量读取，代码中不得有兜底值。
"""
import importlib

import pytest

from orchestrator import llm


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "MODEL_FAST", "MODEL_SMART"):
        monkeypatch.delenv(var, raising=False)
    llm.client.cache_clear()
    yield
    llm.client.cache_clear()


def test_import_safe_without_keys():
    """无密钥环境下 import 与重载均不得读密钥。"""
    importlib.reload(llm)


def test_missing_api_key_raises_clear_error():
    with pytest.raises(llm.MissingApiKeyError, match="DEEPSEEK_API_KEY"):
        llm.client()


def test_missing_base_url_raises_clear_error(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    with pytest.raises(llm.MissingApiKeyError, match="DEEPSEEK_BASE_URL"):
        llm.client()


def test_missing_model_raises_clear_error(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid")
    with pytest.raises(llm.MissingApiKeyError, match="MODEL_SMART"):
        llm.chat([{"role": "user", "content": "hi"}], tier="smart")
