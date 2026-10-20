"""GPT-Researcher retriever 插件：DeepSeek Search/Fetch 检索腿。

- web_search / web_fetch：两个独立工具函数（FR-009，仓库内唯一实现）
- DeepSeekSearchRetriever：GPT-R 鸭子类型 retriever（复用工具函数）
"""
from .client import web_fetch, web_search
from .deepseek import DeepSeekSearchRetriever

__all__ = ["DeepSeekSearchRetriever", "web_fetch", "web_search"]
