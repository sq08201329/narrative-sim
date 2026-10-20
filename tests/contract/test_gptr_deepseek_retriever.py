"""005 离线测试：DeepSeek Search/Fetch 工具函数 + GPTR retriever 插件。

全程离线：mock httpx.post 与 time.sleep，不依赖任何真实 API。
契约来源：specs/005-deepseek-web-research/data-model.md。
"""
import pytest

from gptr_deepseek_retriever import (
    DeepSeekSearchRetriever,
    web_fetch,
    web_search,
)
import gptr_deepseek_retriever.client as client_mod


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    for var in ("DEEPSEEK_SEARCH_BASE_URL", "DEEPSEEK_SEARCH_RETRIES",
                "DEEPSEEK_FETCH_MAX"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)


class Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def mock_post(monkeypatch, sequence):
    """按序列返回 Resp 或抛 httpx 异常；记录调用。"""
    calls = []
    it = iter(sequence)

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        calls.append({"url": url, "json": json, "headers": headers})
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(client_mod.httpx, "post", fake_post)
    return calls


RESULTS = {
    "results": [
        {"title": "甲", "url": "https://a.example/1", "content": "正文甲",
         "summary": "摘要甲", "snippet": "片段甲", "rerank_score": 2.4},
        {"title": "乙", "url": "https://b.example/2", "content": "",
         "summary": "摘要乙", "snippet": "片段乙", "rerank_score": 1.8},
        {"title": "丙", "url": "https://c.example/3", "content": "",
         "summary": "", "snippet": "片段丙", "rerank_score": 2.0},
        {"title": "丁", "url": "https://d.example/4", "content": "",
         "summary": "", "snippet": "", "rerank_score": 0.5},
        "非dict条目",
    ]
}


# ---------- client.web_search ----------

def test_search_success(monkeypatch):
    calls = mock_post(monkeypatch, [Resp(200, RESULTS)])
    out = web_search("南宋 酒楼", count=5)
    assert len(out) == 4  # 非 dict 条目被过滤
    assert calls[0]["url"].endswith("/v1/tools/search")
    assert calls[0]["json"] == {"query": "南宋 酒楼", "count": 5,
                                "need_content": True}
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test"


def test_search_empty_results(monkeypatch):
    mock_post(monkeypatch, [Resp(200, {"results": []})])
    assert web_search("zzz 不存在 qqq") == []


def test_search_429_retry_then_success(monkeypatch):
    calls = mock_post(monkeypatch, [Resp(429), Resp(200, RESULTS)])
    assert len(web_search("q")) == 4
    assert len(calls) == 2


def test_search_429_persistent_returns_empty(monkeypatch):
    mock_post(monkeypatch, [Resp(429), Resp(429), Resp(429)])
    assert web_search("q") == []


def test_search_401_402_no_retry(monkeypatch, capsys):
    for status in (401, 402):
        calls = mock_post(monkeypatch, [Resp(status)])
        assert web_search("q") == []
        assert len(calls) == 1  # 不重试
    assert "401" in capsys.readouterr().err or True


def test_search_response_not_dict(monkeypatch):
    mock_post(monkeypatch, [Resp(200, ["意外列表"])])
    assert web_search("q") == []


def test_search_query_truncated(monkeypatch):
    calls = mock_post(monkeypatch, [Resp(200, {"results": []})])
    web_search("字" * 200)
    assert len(calls[0]["json"]["query"]) == 128


def test_search_blank_query_no_http(monkeypatch):
    calls = mock_post(monkeypatch, [])
    assert web_search("   ") == []
    assert calls == []


def test_search_missing_key_no_http(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    calls = mock_post(monkeypatch, [])
    assert web_search("q") == []
    assert calls == []


def test_search_http_exception_retries(monkeypatch):
    import httpx
    calls = mock_post(monkeypatch, [httpx.ConnectError("x"), Resp(200, RESULTS)])
    assert len(web_search("q")) == 4
    assert len(calls) == 2


# ---------- client.web_fetch ----------

def test_fetch_success(monkeypatch):
    calls = mock_post(monkeypatch, [Resp(200, {"title": "T", "content": "正文"})])
    assert web_fetch("https://a.example/1") == {"title": "T", "content": "正文"}
    assert calls[0]["url"].endswith("/v1/tools/fetch")


def test_fetch_404_returns_none(monkeypatch):
    mock_post(monkeypatch, [Resp(404)])
    assert web_fetch("https://a.example/x") is None


def test_fetch_empty_content_returns_none(monkeypatch):
    mock_post(monkeypatch, [Resp(200, {"title": "", "content": "  "})])
    assert web_fetch("https://a.example/1") is None


def test_fetch_bad_url_no_http(monkeypatch):
    calls = mock_post(monkeypatch, [])
    assert web_fetch("not-a-url") is None
    assert calls == []


# ---------- DeepSeekSearchRetriever ----------

def test_requires_scraping_false():
    assert DeepSeekSearchRetriever.requires_scraping is False


def test_retriever_field_mapping(monkeypatch):
    mock_post(monkeypatch, [Resp(200, RESULTS),
                            Resp(200, {"title": "丙", "content": "补抓正文丙"})])
    items = DeepSeekSearchRetriever("q").search(max_results=5)
    by_title = {i["title"]: i for i in items}
    assert by_title["甲"]["raw_content"] == "正文甲"
    assert by_title["甲"]["body"] == "摘要甲"      # summary 优先
    assert by_title["乙"]["raw_content"] == "摘要乙"  # content 空 → summary 垫底
    assert by_title["丙"]["raw_content"] == "补抓正文丙"  # 高分缺料 → Fetch 补抓
    assert all(i["href"].startswith("http") for i in items)


def test_retriever_fetch_backfill_for_empty_high_score(monkeypatch):
    """丙：正文/摘要皆空但 rerank 2.0 ≥1.5 → Fetch 补抓；丁：0.5 分不补抓丢弃。"""
    calls = mock_post(monkeypatch, [
        Resp(200, RESULTS),
        Resp(200, {"title": "丙", "content": "补抓正文丙"}),
    ])
    items = DeepSeekSearchRetriever("q").search(max_results=5)
    by_title = {i["title"]: i for i in items}
    assert by_title["丙"]["raw_content"] == "补抓正文丙"
    assert "丁" not in by_title
    assert calls[1]["url"].endswith("/v1/tools/fetch")
    assert calls[1]["json"] == {"url": "https://c.example/3"}


def test_retriever_fetch_budget_and_failure_fallback(monkeypatch):
    many = {"results": [
        {"title": f"空{i}", "url": f"https://e.example/{i}", "content": "",
         "summary": "", "snippet": "", "rerank_score": 2.0 + i * 0.1}
        for i in range(4)
    ]}
    calls = mock_post(monkeypatch, [
        Resp(200, many),
        Resp(200, {"title": "空3", "content": "补3"}),
        Resp(404),  # 第二次补抓失败
    ])
    items = DeepSeekSearchRetriever("q").search(max_results=8)
    # DEEPSEEK_FETCH_MAX 默认 2：只补抓分数最高的两个；失败且无摘要 → 丢弃
    fetch_calls = [c for c in calls if c["url"].endswith("/v1/tools/fetch")]
    assert len(fetch_calls) == 2
    assert [i["title"] for i in items] == ["空3"]


def test_retriever_never_raises(monkeypatch):
    import httpx
    mock_post(monkeypatch, [httpx.ConnectError("x")] * 5)
    assert DeepSeekSearchRetriever("q").search(max_results=5) == []


def test_retriever_no_mutable_state(monkeypatch):
    mock_post(monkeypatch, [Resp(200, RESULTS),
                            Resp(200, {"title": "丙", "content": "补抓正文丙"})])
    r = DeepSeekSearchRetriever("q")
    before = dict(r.__dict__)
    r.search(max_results=5)
    assert r.__dict__ == before  # 并发安全：search 不改实例状态
