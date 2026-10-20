"""DeepSeek Search/Fetch 官方 API 工具函数（FR-009：仓库内唯一实现）。

契约（data-model.md「工具函数契约」）：
- 任何路径不抛异常：失败返回 [] / None，原因 print 到 stderr
- 429/408/5xx 退避 2s/4s 重试，上限 DEEPSEEK_SEARCH_RETRIES（默认 2）
- 401/402 打印原因不重试；query 截断到官方上限 128 字符；超时 30s
"""
import os
import sys
import time

import httpx

DEFAULT_BASE_URL = "https://api.deepseek.com"
QUERY_MAX_CHARS = 128
REQUEST_TIMEOUT = 30.0
BACKOFF_S = (2, 4)


def _warn(msg: str) -> None:
    print(f"[gptr-deepseek] {msg}", file=sys.stderr)


def _base_url() -> str:
    return os.environ.get("DEEPSEEK_SEARCH_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _api_key() -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        _warn("缺少 DEEPSEEK_API_KEY，检索不可用")
        return None
    return key


def _retries() -> int:
    return int(os.environ.get("DEEPSEEK_SEARCH_RETRIES", "2"))


def _post(path: str, payload: dict):
    """带退避重试的 POST。成功返回 parsed JSON dict；失败返回 None（不抛）。"""
    key = _api_key()
    if key is None:
        return None
    url = f"{_base_url()}{path}"
    headers = {"Authorization": f"Bearer {key}"}
    attempts = 1 + _retries()
    for i in range(attempts):
        try:
            resp = httpx.post(url, json=payload, headers=headers,
                              timeout=REQUEST_TIMEOUT)
        except httpx.HTTPError as exc:
            _warn(f"请求异常: {exc}")
            if i < attempts - 1:
                time.sleep(BACKOFF_S[min(i, len(BACKOFF_S) - 1)])
            continue
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                _warn("响应非 JSON")
                return None
            if not isinstance(data, dict):
                _warn(f"响应类型异常: {type(data).__name__}")
                return None
            return data
        if resp.status_code in (401, 402):
            _warn(f"鉴权/余额问题（HTTP {resp.status_code}），不重试")
            return None
        if resp.status_code in (408, 429) or resp.status_code >= 500:
            _warn(f"HTTP {resp.status_code}，退避重试 {i + 1}/{attempts - 1}")
            if i < attempts - 1:
                time.sleep(BACKOFF_S[min(i, len(BACKOFF_S) - 1)])
            continue
        _warn(f"HTTP {resp.status_code}（不可重试）: {resp.text[:200]}")
        return None
    return None


def web_search(query: str, count: int = 8, need_content: bool = True) -> list[dict]:
    """DeepSeek Search：成功返回 results 条目列表；无结果/失败返回 []。"""
    if not query or not query.strip():
        return []
    q = query[:QUERY_MAX_CHARS]
    if len(q) < len(query):
        _warn(f"query 超长，已截断到 {QUERY_MAX_CHARS} 字符")
    data = _post("/v1/tools/search",
                 {"query": q, "count": count, "need_content": need_content})
    if data is None:
        return []
    results = data.get("results")
    if not isinstance(results, list):
        _warn("results 字段异常")
        return []
    return [r for r in results if isinstance(r, dict)]


def web_fetch(url: str) -> dict | None:
    """DeepSeek Fetch：成功返回 {title, content}；403/404/失败返回 None。"""
    if not url or not url.startswith(("http://", "https://")):
        return None
    data = _post("/v1/tools/fetch", {"url": url})
    if data is None:
        return None
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return {"title": data.get("title") or "", "content": content}
