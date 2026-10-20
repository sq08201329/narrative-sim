"""GPT-Researcher retriever：DeepSeek Search 检索腿。

鸭子类型契约（fork 源码核实，research.md R1/R2）：
- 构造 (query, headers=None, query_domains=None)
- search(max_results=...) 同步（调用方 asyncio.to_thread 包装）
- 返回 [{"href", "raw_content", "body", "title"}]，至少含 href
- requires_scraping = False 显式声明：raw_content 即全文，
  GPT-R 不再对同源发起网页抓取（researcher.py:903-915）
- 任何路径不抛异常（初始搜索路径无 try 兜底，抛出会炸掉整个调研）
"""
import os

from .client import web_fetch, web_search

FETCH_SCORE_THRESHOLD = 1.5  # rerank_score ≥ 此值且材料皆空才补抓


class DeepSeekSearchRetriever:
    """DeepSeek Search API retriever（entry-point 注册名 deepseek）。"""

    requires_scraping = False

    def __init__(self, query, headers=None, query_domains=None):
        self.query = query
        self.headers = headers
        self.query_domains = query_domains

    def search(self, max_results=10):
        try:
            results = web_search(self.query, count=max_results,
                                 need_content=True)
        except Exception as exc:  # client 契约是不抛，这里再兜一层
            print(f"[gptr-deepseek] search 异常兜底: {exc}")
            return []
        return self._map(results)

    def _map(self, results: list[dict]) -> list[dict]:
        fetch_budget = int(os.environ.get("DEEPSEEK_FETCH_MAX", "2"))
        # 补抓候选：正文与摘要皆空且排序分达标，按分数降序
        candidates = sorted(
            (r for r in results
             if not (r.get("content") or "").strip()
             and not (r.get("summary") or "").strip()
             and (r.get("rerank_score") or 0) >= FETCH_SCORE_THRESHOLD),
            key=lambda r: r.get("rerank_score") or 0, reverse=True)
        fetched: dict[int, str] = {}
        for r in candidates[:fetch_budget]:
            page = web_fetch(r.get("url", ""))
            if page:
                fetched[id(r)] = page["content"]

        items = []
        for r in results:
            url = (r.get("url") or "").strip()
            if not url:
                continue
            raw = ((r.get("content") or "").strip()
                   or fetched.get(id(r), "")
                   or (r.get("summary") or "").strip())
            if not raw:
                continue
            items.append({
                "href": url,
                "raw_content": raw,
                "body": (r.get("summary") or r.get("snippet") or "").strip(),
                "title": r.get("title") or "",
            })
        return items
