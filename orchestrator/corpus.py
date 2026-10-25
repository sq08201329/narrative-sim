"""古籍腿业务（016 US2，宪章 II 胶水层）。

- corpus_materials：db/corpus.py 检索 top-k → LLM 转写（古文→现代汉语，
  保留专有名词）→ 戏库原料表（retriever=corpus:<书名>·<篇目>，009 漏斗
  同 query 天然复用）
- corpus_knowledge：DM 史料源装配（检索块拼预算，world.py 用）
- 库缺失 → CorpusUnavailable（调用方降级），零命中 → []
"""
import os
from pathlib import Path

CORPUS_DB_ENV = "CORPUS_DB"
_DEFAULT_DB = "data/corpus.db"


class CorpusUnavailable(RuntimeError):
    """古籍库未建/路径不存在。"""


def _db_path() -> str:
    p = os.environ.get(CORPUS_DB_ENV, _DEFAULT_DB)
    if not Path(p).exists():
        raise CorpusUnavailable(f"古籍库不存在: {p}（先跑 corpus_ingest）")
    return p


def corpus_materials(query: str, store, top_k: int = 3,
                     link_asset_id: str | None = None,
                     chat=None) -> list[int]:
    """古籍腿：检索 → 转写 → 入原料表。返回原料行 id 列表。"""
    from db.corpus import search

    hits = search(_db_path(), query, limit=top_k)["hits"]
    if not hits:
        return []
    if chat is None:
        from .llm import chat as _chat
        chat = _chat
    ids = []
    for h in hits:
        transcription = chat([
            {"role": "user", "content": (
                "以下为古籍原文，请给出忠实于原文的现代汉语摘要"
                "（100 字内，保留专有名词原字）：\n" + h["text"])}])
        context = (f"{h['text']}\n\n【现代汉语转写】\n{transcription}")
        retriever = f"corpus:{h['title']}·{h['heading_path'] or '全文'}"
        ids.append(store.put_material(
            link_asset_id or "lore:research", query, retriever, context))
    return ids


def corpus_knowledge(query: str, budget: int) -> str:
    """DM 史料源：检索块拼进预算（R4）。库缺失/零命中返回 ""。"""
    try:
        from db.corpus import search
        hits = search(_db_path(), query, limit=3)["hits"]
    except CorpusUnavailable:
        return ""
    parts, used = [], 0
    for h in hits:
        chunk = f"【{h['title']}·{h['heading_path']}】{h['text'][:500]}"
        if used + len(chunk) > budget:
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts)
