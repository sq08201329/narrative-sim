"""调研管线：gptr-mcp 客户端 + chat_json 结构化 + 语义去重（宪章原则 II/IV 接缝）。

GPT-Researcher 栈（gptr-mcp 服务 → SearXNG）的全部接触面集中在本模块：
- MCP 客户端封装：streamable-http 连接 GPTR_MCP_URL，call_tool 为可 mock 接缝
- 管线 research_asset()：deep_research → llm.chat_json 抽取 → 溯源填充 →
  语义去重 → store.put_asset() 校验入库；任何失败零部分写入
- 去重：嵌入不可用（配置缺失/预检失败/调用异常）时降级为名称精确匹配
"""
import asyncio
import hashlib
import json
import logging
import math
import os
from datetime import datetime, timezone

from . import embedding as _embedding_mod
from . import llm as _llm

logger = logging.getLogger(__name__)

TYPE_PREFIX = {"character": "char", "prop": "prop", "scene": "scene", "epoch": "epoch"}
EXTRACTION_RETRIES = 2  # 首次 + 重试 1 次


class ResearchError(RuntimeError):
    """调研管线失败（配置缺失 / 服务不可达 / 抽取失败 / 契约拒绝）。"""


# ---------- MCP 客户端 ----------

def _mcp_url() -> str:
    url = os.environ.get("GPTR_MCP_URL", "").strip()
    if not url:
        raise ResearchError(
            "未设置 GPTR_MCP_URL：请在 .env 中配置 gptr-mcp 服务端地址"
        )
    return url


async def _mcp_call_tool(url: str, name: str, arguments: dict, timeout: float) -> dict:
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    http_client = httpx2.AsyncClient(timeout=httpx2.Timeout(timeout))
    async with streamable_http_client(url, http_client=http_client) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None)
    if structured is not None:
        return structured
    return json.loads(result.content[0].text)


def _default_call_tool():
    url = _mcp_url()
    timeout = float(os.environ.get("RESEARCH_TIMEOUT_S", "180"))

    def call(name: str, arguments: dict) -> dict:
        return asyncio.run(_mcp_call_tool(url, name, arguments, timeout))

    return call


# ---------- 抽取与组装 ----------

_TYPE_GUIDE = {
    "character": "人物：必须给出 appearance.visual_prompt（英文视觉提示词骨架）、"
                 "appearance.description，以及 persona_spec（age/occupation/"
                 "personality/beliefs/speech_style 五字段）",
    "scene": "场景：必须给出 appearance.visual_prompt（英文视觉提示词骨架）"
             "与 appearance.description（布局、陈设、氛围）",
    "prop": "道具：必须给出 appearance.visual_prompt 与 appearance.description"
            "（材质、形制、纹饰）",
    "epoch": "时代：给出 historical_context.epoch/region 与时代特征描述",
}


def _build_prompt(query: str, asset_type: str, context: str) -> list[dict]:
    return [
        {"role": "system", "content":
         "你是资产结构化助手。根据调研材料抽取资产信息，输出严格 JSON 对象，"
         "不要输出任何额外文字。JSON 必须包含 type、name 字段；"
         f"{_TYPE_GUIDE[asset_type]}。不得编造调研材料中没有的事实，"
         "可在风格描述上合理加工。"},
        {"role": "user", "content":
         f"资产类型：{asset_type}\n调研主题：{query}\n\n调研材料：\n{context}"},
    ]


def _compose_asset(draft: dict, asset_type: str, source_urls: list[str], now) -> dict:
    name = str(draft.get("name") or "").strip()
    if not name:
        raise ResearchError("抽取结果缺少 name 字段")
    asset_id = f"{TYPE_PREFIX[asset_type]}_{hashlib.sha1(name.encode('utf-8')).hexdigest()[:10]}"
    ts = now() if now is not None else datetime.now(timezone.utc).isoformat()
    try:
        model_name = _llm._model("fast")
    except Exception:
        model_name = os.environ.get("MODEL_FAST", "unknown")
    asset = dict(draft)
    asset.update({
        "asset_id": asset_id,
        "type": asset_type,
        "name": name,
        "provenance": {
            "researched_at": ts,
            "retriever": "gptr-mcp(searxng)",
            "model": model_name,
            "confidence": min(0.5 + 0.1 * len(source_urls), 0.9),
        },
        "historical_context": {
            **(draft.get("historical_context") or {}),
            "sources": list(source_urls),
        },
    })
    return asset


# ---------- 语义去重 ----------

def _dedup_text(asset: dict) -> str:
    appearance = asset.get("appearance") or {}
    parts = [asset.get("name", ""),
             appearance.get("description", ""),
             appearance.get("visual_prompt", "")]
    return " ".join(p for p in parts if p)


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _find_duplicate(asset: dict, store, embed) -> str | None:
    candidates = store.list_assets(asset["type"])
    if not candidates:
        return None
    embed_fn = embed if embed is not None else _embedding_mod.embed_texts
    vecs = embed_fn([_dedup_text(asset)] + [_dedup_text(c) for c in candidates])
    if vecs is None:
        logger.warning("嵌入服务不可用，去重降级为名称精确匹配")
        for c in candidates:
            if c.get("name") == asset["name"]:
                return c["asset_id"]
        return None
    threshold = float(os.environ.get("RESEARCH_DEDUP_THRESHOLD", "0.85"))
    best_sim, best_id = 0.0, None
    for c, v in zip(candidates, vecs[1:]):
        sim = _cos(vecs[0], v)
        if sim > best_sim:
            best_sim, best_id = sim, c["asset_id"]
    if best_id is not None and best_sim >= threshold:
        logger.info("语义去重命中已有资产 %s（cos=%.3f）", best_id, best_sim)
        return best_id
    return None


# ---------- 管线入口 ----------

def research_asset(query: str, asset_type: str, store, *,
                   call_tool=None, chat_json=None, embed=None, now=None) -> str:
    """查询词 → 契约资产入库，返回 asset_id；重复资产返回已有 asset_id。

    失败一律抛 ResearchError，且不会产生任何部分写入。
    call_tool / chat_json / embed / now 为测试注入接缝。
    """
    if not query or not query.strip():
        raise ResearchError("查询词为空或仅含空白字符")
    if asset_type not in TYPE_PREFIX:
        raise ResearchError(f"不支持的资产类型: {asset_type}")

    if call_tool is None:
        call_tool = _default_call_tool()  # 内部先做 GPTR_MCP_URL 检查

    try:
        resp = call_tool("deep_research", {"query": query})
    except ResearchError:
        raise
    except Exception as exc:
        raise ResearchError(f"调研服务调用失败: {exc}") from exc

    if not isinstance(resp, dict) or resp.get("status") != "success":
        raise ResearchError(f"调研服务返回错误: {resp}")
    source_urls = resp.get("source_urls") or []
    if not source_urls:
        raise ResearchError("调研结果无来源，拒绝入库")
    context = resp.get("context") or ""

    chat = chat_json if chat_json is not None else _llm.chat_json
    draft, last_err = None, None
    for _ in range(EXTRACTION_RETRIES):
        try:
            draft = chat(_build_prompt(query, asset_type, context))
            break
        except Exception as exc:  # JSON 漂移等
            last_err = exc
    if draft is None:
        raise ResearchError(f"结构化抽取失败（重试 {EXTRACTION_RETRIES} 次）: {last_err}")

    asset = _compose_asset(draft, asset_type, source_urls, now)

    duplicate = _find_duplicate(asset, store, embed)
    if duplicate is not None:
        return duplicate

    try:
        return store.put_asset(asset)
    except Exception as exc:
        raise ResearchError(f"资产契约校验失败: {exc}") from exc
