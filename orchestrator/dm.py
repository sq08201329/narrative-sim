"""DM 裁决提供者薄工厂（010，宪章原则 II/VI 接缝）。

- build_dm_provider：环境桥接（DEEPSEEK_*→OPENAI_* 仅补缺，002 模式）+
  构造引擎自带 LiteLLMDMProvider（research.md R1/R2）
- build_dm_knowledge：调研原料 → scene.dm_knowledge 文本，预算截断（R4）
"""
import os

from .store import Store


class DMConfigError(RuntimeError):
    """裁决配置缺口（密钥/环境变量缺失）。"""


def build_dm_provider(options):
    """构造真实裁决者。缺密钥抛 DMConfigError（消息含缺失键名）。

    桥接仅补缺：已有 OPENAI_* 永不覆盖。模型串 openai/{options.model}
    （litellm openai provider 原生读 OPENAI_BASE_URL）。
    """
    from worldseed.dm.providers.llm import LiteLLMDMProvider

    if not os.environ.get("OPENAI_API_KEY"):
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise DMConfigError(
                "缺少环境变量 DEEPSEEK_API_KEY（或 OPENAI_API_KEY）："
                "启用 --dm 前请在环境或 .env 中配置"
            )
        os.environ["OPENAI_API_KEY"] = key
    if not os.environ.get("OPENAI_BASE_URL"):
        base = os.environ.get("DEEPSEEK_BASE_URL")
        if base:
            os.environ["OPENAI_BASE_URL"] = base

    return LiteLLMDMProvider(
        model=f"openai/{options.model}",
        timeout=options.timeout_s,
        max_retries=options.max_retries,
    )


def build_dm_knowledge(store: Store, asset_ids: list[str],
                       budget: int = 2000) -> str:
    """汇总各资产调研原料为 dm_knowledge 文本。

    每条渲染为 "【query】context前N字"；加上整条会超预算时停止
    （尾部整条丢弃）。无原料返回 ""。永不抛异常。
    """
    parts: list[str] = []
    used = 0
    for aid in asset_ids:
        try:
            materials = store.get_materials(aid)
        except Exception:
            continue
        for m in materials:
            chunk = f"【{m['query']}】{m['context'][:500]}"
            if used + len(chunk) > budget:
                return "\n".join(parts)
            parts.append(chunk)
            used += len(chunk)
    return "\n".join(parts)
