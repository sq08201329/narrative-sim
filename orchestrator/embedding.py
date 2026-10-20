"""共享嵌入服务接入（003 自 persona_tinytroupe 搬入，004 起供调研管线复用）。

OpenAI 兼容嵌入端点（如本机 litert-lm）的配置、预检与客户端构造：
- model_name= 绕开 OpenAIEmbeddingModelType 枚举白名单
- 文档/查询分别补 EmbeddingGemma 2 任务前缀（litert-lm 服务端不加）
- 空文本不发请求、超长截断；异常/超时返回零向量，调用方不崩溃
"""
import logging
import os

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768
DOC_PREFIX = "task: search result | text: "
QUERY_PREFIX = "task: search query | text: "
DEFAULT_EMBEDDING_MODEL = "eg2-text-270m.litertlm"


def embedding_config() -> dict | None:
    """从环境变量读取嵌入服务配置；EMBEDDING_API_BASE 未设返回 None（走降级）。"""
    base = os.environ.get("EMBEDDING_API_BASE", "").strip()
    if not base:
        return None
    return {
        "api_base": base.rstrip("/"),
        "model": os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        "timeout_s": float(os.environ.get("EMBEDDING_TIMEOUT_S", "10")),
        "max_chars": int(os.environ.get("EMBEDDING_MAX_CHARS", "2000")),
    }


def preflight_embedding(cfg: dict) -> str | None:
    """可达性 + 模型身份预检。返回 None 表示通过，否则返回失败原因。"""
    import httpx

    try:
        r = httpx.get(f"{cfg['api_base']}/models", timeout=5)
        r.raise_for_status()
        ids = [m.get("id") for m in r.json().get("data", [])]
        if cfg["model"] not in ids:
            return f"模型 {cfg['model']} 不在服务模型列表 {ids}"
        e = httpx.post(
            f"{cfg['api_base']}/embeddings",
            json={"model": cfg["model"], "input": "ping"},
            timeout=min(cfg["timeout_s"], 10),
        )
        e.raise_for_status()
        dim = len(e.json()["data"][0]["embedding"])
        if dim != EMBEDDING_DIM:
            return f"向量维度 {dim} != {EMBEDDING_DIM}"
    except Exception as exc:
        return f"嵌入服务预检失败: {exc}"
    return None


def build_embedding_model(cfg: dict):
    """构造带任务前缀与失败兜底的嵌入模型。

    - model_name= 绕开 OpenAIEmbeddingModelType 枚举白名单
    - 文档/查询分别补 EmbeddingGemma 2 任务前缀（litert-lm 服务端不加）
    - 空文本不发请求、超长截断；异常/超时返回零向量，仿真不崩溃
    """
    from llama_index.embeddings.openai import OpenAIEmbedding

    max_chars = cfg["max_chars"]
    zero = [0.0] * EMBEDDING_DIM

    class PrefixedEmbedding(OpenAIEmbedding):
        _failure_logged = False

        def _fallback(self, reason) -> list[float]:
            if not PrefixedEmbedding._failure_logged:
                logger.warning("嵌入调用失败，返回零向量（后续失败不再重复日志）: %s", reason)
                PrefixedEmbedding._failure_logged = True
            return list(zero)

        def _prepare(self, text: str) -> str | None:
            if not text or not text.strip():
                return None
            return text[:max_chars]

        def _get_query_embedding(self, query: str) -> list[float]:
            text = self._prepare(query)
            if text is None:
                return list(zero)
            try:
                return super()._get_query_embedding(QUERY_PREFIX + text)
            except Exception as exc:
                return self._fallback(exc)

        def _get_text_embedding(self, text: str) -> list[float]:
            prepared = self._prepare(text)
            if prepared is None:
                return list(zero)
            try:
                return super()._get_text_embedding(DOC_PREFIX + prepared)
            except Exception as exc:
                return self._fallback(exc)

        def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            prepared = [self._prepare(t) for t in texts]
            try:
                vecs = super()._get_text_embeddings(
                    [DOC_PREFIX + t for t in prepared if t is not None]
                )
            except Exception as exc:
                return [self._fallback(exc) for _ in texts]
            it = iter(vecs)
            return [next(it) if t is not None else list(zero) for t in prepared]

    return PrefixedEmbedding(
        model_name=cfg["model"],
        api_base=cfg["api_base"],
        api_key="local-embedding",
        embed_batch_size=10,
        timeout=cfg["timeout_s"],
        max_retries=1,
    )


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """独立调用入口（调研去重用）：配置缺失/预检失败返回 None（调用方走降级），
    否则返回每条文本的 768 维向量（单条失败为零向量）。"""
    cfg = embedding_config()
    if cfg is None:
        return None
    if preflight_embedding(cfg) is not None:
        return None
    model = build_embedding_model(cfg)
    return [model.get_text_embedding(t) for t in texts]
