"""LLM 统一接缝：DeepSeek Flash（OpenAI 兼容协议）。

宪章原则 VI：模型名与密钥只从环境变量读取，不落代码。
import 本模块不读密钥；首次调用时缺少 DEEPSEEK_API_KEY 会抛出明确错误。
M1 最小链路不调用本模块。
"""
import os
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class MissingApiKeyError(RuntimeError):
    """缺少 LLM 密钥/服务地址环境变量。"""


@lru_cache(maxsize=1)
def client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise MissingApiKeyError(
            "缺少环境变量 DEEPSEEK_API_KEY：请复制 .env.example 为 .env 并填入 DeepSeek key"
        )
    base_url = os.environ.get("DEEPSEEK_BASE_URL")
    if not base_url:
        raise MissingApiKeyError(
            "缺少环境变量 DEEPSEEK_BASE_URL：请在 .env 中配置服务地址"
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def _model(tier: str) -> str:
    var = "MODEL_SMART" if tier == "smart" else "MODEL_FAST"
    model = os.environ.get(var)
    if not model:
        raise MissingApiKeyError(f"缺少环境变量 {var}：请在 .env 中配置模型名")
    return model


def chat(messages: list[dict], tier: str = "fast", **kwargs) -> str:
    resp = client().chat.completions.create(
        model=_model(tier), messages=messages, **kwargs
    )
    return resp.choices[0].message.content


def chat_json(messages: list[dict], tier: str = "fast") -> dict:
    import json

    out = chat(messages, tier=tier, response_format={"type": "json_object"})
    return json.loads(out)
