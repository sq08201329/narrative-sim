"""立项调研纲领（009）：题材 → 三类清单 → 批量执行（四层防重复漏斗）。

- generate_brief：chat_json 把题材拆解为 世界/人物/剧情 三类清单
  （漂移重试 1 次；BRIEF_MAX_ITEMS 闸门；三类各 ≥1 条）
- execute_brief：逐条执行，四层漏斗拦截重复（research.md R4）：
  ① 精确缓存（get_material_by_query）→ ② 清单内语义合并 →
  ③ 库内高置信复用（资产类跳过调研）→ ④ 中阈值 attach（原料挂已有资产）
- 资产类调 research_asset（004 管线复用，FR-003）；素材类调 research_material
"""
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

from . import embedding as _embedding_mod
from . import llm as _llm
from .research import (
    ResearchError,
    _cos,
    _dedup_text,
    research_asset,
    research_material,
)

logger = logging.getLogger(__name__)

CATEGORIES = ("world", "character", "lore")
ASSET_TYPES = ("character", "scene", "prop", "epoch")


class BriefError(RuntimeError):
    """立项生成或清单非法。"""


def _skip_threshold() -> float:
    return float(os.environ.get("RESEARCH_SKIP_THRESHOLD", "0.88"))


def _attach_threshold() -> float:
    return float(os.environ.get("RESEARCH_ATTACH_THRESHOLD", "0.80"))


def _slug(theme: str) -> str:
    return hashlib.sha1(theme.encode("utf-8")).hexdigest()[:8]


# ---------- 生成 ----------

def _build_brief_prompt(theme: str, limit: int) -> list[dict]:
    return [
        {"role": "system", "content":
         "你是影视前期策划。把题材拆解为调研清单，输出严格 JSON 对象，不要任何额外文字。"
         "格式：{\"items\": [{\"category\": ..., \"query\": ..., \"asset_type\": ...}]}。"
         "规则：category 三值——world（时代/场景/道具等世界素材）、"
         "character（人物素材）、lore（剧情素材：真实事件/制度/行业生态/民俗）。"
         "world 与 character 的 asset_type 取 character/scene/prop/epoch；"
         "lore 的 asset_type 为 null。query 是可直接用于网络调研的具体查询词。"
         "三个 category 都必须至少 1 条，总数不超过限制。"},
        {"role": "user", "content": f"题材：{theme}\n条数上限：{limit}"},
    ]


def _validate_items(data: dict, limit: int) -> tuple[list[dict], bool]:
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise BriefError("清单为空或格式非法")
    valid = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cat = it.get("category")
        query = str(it.get("query") or "").strip()
        atype = it.get("asset_type")
        if cat not in CATEGORIES or not query:
            continue
        if cat == "lore":
            atype = None
        elif atype not in ASSET_TYPES:
            continue
        valid.append({"category": cat, "query": query, "asset_type": atype,
                      "link": it.get("link")})
    seen = {v["category"] for v in valid}
    if seen != set(CATEGORIES):
        raise BriefError(f"清单类别不全（缺 {set(CATEGORIES) - seen}）")
    truncated = len(valid) > limit
    return valid[:limit], truncated


def generate_brief(theme: str, *, chat_json=None, max_items: int | None = None) -> dict:
    if not theme or len(theme.strip()) < 4:
        raise BriefError("题材描述过短（至少 4 个字符）")
    limit = max_items or int(os.environ.get("BRIEF_MAX_ITEMS", "12"))
    chat = chat_json if chat_json is not None else _llm.chat_json
    last_err = None
    for _ in range(2):
        try:
            data = chat(_build_brief_prompt(theme.strip(), limit))
            items, truncated = _validate_items(data, limit)
            return {"theme": theme.strip(),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "items": items, "truncated": truncated}
        except Exception as exc:  # JSON 漂移 / 类别缺失：重试一次（spec 边界）
            last_err = exc
    raise BriefError(f"清单生成失败（重试 2 次）: {last_err}")


# ---------- 漏斗辅助 ----------

def _match_existing(query: str, store, embed) -> tuple[str, float] | None:
    """库内最相似资产（asset_id, cos）；嵌入不可用降级名称精确匹配。"""
    assets = store.list_assets()
    if not assets:
        return None
    embed_fn = embed if embed is not None else _embedding_mod.embed_texts
    vecs = embed_fn([query] + [_dedup_text(a) for a in assets])
    if vecs is None:
        logger.warning("嵌入服务不可用，复用匹配降级为名称精确匹配")
        for a in assets:
            if a.get("name") == query:
                return a["asset_id"], 1.0
        return None
    best_sim, best_id = 0.0, None
    for a, v in zip(assets, vecs[1:]):
        sim = _cos(vecs[0], v)
        if sim > best_sim:
            best_sim, best_id = sim, a["asset_id"]
    return (best_id, best_sim) if best_id else None


def _dedup_within_brief(items: list[dict], embed) -> tuple[list[dict], list[str]]:
    """清单内语义合并（FR-010）：同 category 内 cos ≥ skip 阈值的后来者
    并入先到者（跨类别文本相似不合并——调研意图不同）。
    返回 (保留条目, 被合并的 query 列表)。"""
    if len(items) < 2:
        return items, []
    embed_fn = embed if embed is not None else _embedding_mod.embed_texts
    vecs = embed_fn([it["query"] for it in items])
    if vecs is None:
        return items, []
    threshold = _skip_threshold()
    kept, merged = [], []
    for it, v in zip(items, vecs):
        same_cat = [(kit, kv) for kit, kv in kept if kit["category"] == it["category"]]
        if any(_cos(v, kv) >= threshold for _, kv in same_cat):
            merged.append(it["query"])
        else:
            kept.append((it, v))
    return [it for it, _ in kept], merged


# ---------- 批量执行 ----------

def execute_brief(brief: dict, store, *,
                  research_asset_fn=None, research_material_fn=None,
                  embed=None) -> list[dict]:
    """逐条执行清单（四层漏斗 + 单条容错 + 总账，FR-006/007/009~011）。"""
    ra = research_asset_fn or research_asset
    rm = research_material_fn or research_material
    theme = brief.get("theme", "")
    items = brief.get("items") or []
    ledger: list[dict] = []

    items, merged = _dedup_within_brief(items, embed)
    for q in merged:
        ledger.append({"query": q, "category": "-", "status": "merged",
                       "asset_id": None, "reason": "清单内同义合并"})

    for item in items:
        query, category = item["query"], item["category"]
        entry = {"query": query, "category": category,
                 "status": "failed", "asset_id": None, "reason": None}
        try:
            # ① 精确缓存
            hit = store.get_material_by_query(query)
            if hit is not None:
                entry.update(status="cached", asset_id=hit["asset_id"],
                             reason="精确查询缓存命中")
                ledger.append(entry)
                continue
            # ③ 库内匹配
            match = _match_existing(query, store, embed)
            cos = match[1] if match else 0.0
            if category != "lore" and match and cos >= _skip_threshold():
                entry.update(status="reused", asset_id=match[0],
                             reason=f"库内高置信复用 cos={cos:.3f}")
                ledger.append(entry)
                continue
            link = match[0] if match and cos >= _attach_threshold() else None
            # 执行
            if category == "lore":
                rm(query, store, link_asset_id=link or item.get("link")
                   or f"lore:{_slug(theme)}")
                entry.update(status="attached" if link else "stored",
                             asset_id=link or item.get("link"),
                             reason=f"cos={cos:.3f}" if link else None)
            else:
                before = len(store.list_assets(item["asset_type"]))
                asset_id = ra(query, item["asset_type"], store)
                after = len(store.list_assets(item["asset_type"]))
                entry.update(
                    status="deduplicated" if after == before else "stored",
                    asset_id=asset_id)
        except (ResearchError, BriefError) as e:
            entry["reason"] = str(e)
        except Exception as e:
            entry["reason"] = f"{type(e).__name__}: {e}"
        ledger.append(entry)

    return ledger


def summarize(ledger: list[dict]) -> str:
    counts: dict[str, int] = {}
    for e in ledger:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    parts = [f"{k}={v}" for k, v in sorted(counts.items())]
    return f"共 {len(ledger)} 条: " + ", ".join(parts)
