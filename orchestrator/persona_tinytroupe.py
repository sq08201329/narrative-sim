"""TinyTroupe 真后端：PersonaBackend Protocol 的在线实现（宪章原则 II/IV 接缝）。

所有 TinyTroupe 接触面集中在本文件：
- 环境预检后才懒 import tinytroupe（其 import 即实例化 embedding 客户端，缺 key 会炸）
- OPENAI_API_KEY / OPENAI_BASE_URL 是 openai SDK 原生读取的变量，由 .env 提供；
  仅有 DEEPSEEK_* 时桥接映射
- TinyPerson 实例按 asset_id 缓存（全局注册表重名即报错，实例名直接用 asset_id）
- 动作映射：TALK→dialogue、THINK→inner_voice、DONE 丢弃；emotion 取 cognitive_state
- 语义记忆：EMBEDDING_API_BASE 已设且预检通过时，用 embedding.py 的前缀嵌入模型覆盖
  Settings.embed_model（import 时默认实例会跟随 OPENAI_BASE_URL 指向 LLM 服务，
  必须在首个 TinyPerson 创建前覆盖）；否则降级为本地列表（只存不检）
"""
import logging
import os

from dotenv import load_dotenv

from .embedding import build_embedding_model, embedding_config, preflight_embedding
from .persona import PersonaBackend

logger = logging.getLogger(__name__)

MAX_ACT_RETRIES = 3


class MissingEnvironmentError(RuntimeError):
    """真后端所需环境变量缺失。"""


class BackendActionError(RuntimeError):
    """动作解析重试耗尽后的终极失败。"""


def _register_json_mode_client() -> None:
    """注册 DeepSeek 兼容 client：beta.parse 的 json_schema 被 DeepSeek 拒绝（400），
    改为普通 create + json_object，下游 to_pydantic_or_sanitized_dict 仍做模型校验。"""
    from tinytroupe.clients import register_client
    from tinytroupe.clients.openai_client import OpenAIClient

    class JsonModeClient(OpenAIClient):
        def _raw_model_call(self, model, chat_api_params):
            if "response_format" in chat_api_params:
                params = dict(chat_api_params, response_format={"type": "json_object"})
                params.pop("stream", None)
                return self.client.chat.completions.create(**params)
            return super()._raw_model_call(model, chat_api_params)

    register_client("openai", JsonModeClient())


class TinyTroupeBackend(PersonaBackend):
    def __init__(self, person_cls=None, max_retries: int = MAX_ACT_RETRIES):
        load_dotenv()
        self._bridge_deepseek_env()
        for var in ("OPENAI_API_KEY", "OPENAI_BASE_URL"):
            if not os.environ.get(var):
                raise MissingEnvironmentError(
                    f"缺少环境变量 {var}：请在 .env 中配置（或设置 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL）"
                )
        if person_cls is None:
            _register_json_mode_client()
            self._setup_semantic_mode()
        else:
            self.semantic_mode = "injected"
        self._injected = person_cls is not None
        self._person_cls = person_cls
        self._persons: dict[str, object] = {}
        self._max_retries = max_retries

    def _setup_semantic_mode(self) -> None:
        """预检嵌入服务：通过则覆盖 Settings.embed_model，否则走 002 降级。"""
        cfg = embedding_config()
        reason = "未设置 EMBEDDING_API_BASE" if cfg is None else preflight_embedding(cfg)
        if reason is None:
            from llama_index.core import Settings
            Settings.embed_model = build_embedding_model(cfg)
            self.semantic_mode = "real"
            logger.info("语义记忆：真实嵌入模式（%s）", cfg["model"])
        else:
            self.semantic_mode = f"degraded: {reason}"
            logger.warning("语义记忆降级为本地列表：%s", reason)

    @staticmethod
    def _bridge_deepseek_env() -> None:
        pairs = (("DEEPSEEK_API_KEY", "OPENAI_API_KEY"),
                 ("DEEPSEEK_BASE_URL", "OPENAI_BASE_URL"))
        for src, dst in pairs:
            if not os.environ.get(dst) and os.environ.get(src):
                os.environ[dst] = os.environ[src]

    def _person_class(self):
        if self._person_cls is None:
            from tinytroupe.agent import TinyPerson
            self._person_cls = TinyPerson
        return self._person_cls

    @staticmethod
    def _local_semantic_memory():
        """降级路径（嵌入服务未配置/不可达时）：语义记忆退化为本地列表，只存不检，
        跳过向量连接器（其 add_document/retrieve_relevant 会走 embedding）。"""
        from tinytroupe.agent.memory import SemanticMemory

        class LocalSemanticMemory(SemanticMemory):
            def _store(self, value):
                self.memories.append(value)

            def retrieve_relevant(self, relevance_target, top_k=20):
                return []

        return LocalSemanticMemory()

    def _get_person(self, asset_id: str, persona_spec: dict):
        person = self._persons.get(asset_id)
        if person is None:
            cls = self._person_class()
            if self._injected:
                person = cls(name=asset_id)
            elif self.semantic_mode == "real":
                person = cls(name=asset_id)
            else:
                person = cls(name=asset_id,
                             semantic_memory=self._local_semantic_memory())
            person.include_persona_definitions({
                "age": persona_spec.get("age"),
                "occupation": persona_spec.get("occupation"),
                "personality": persona_spec.get("personality"),
                "beliefs": persona_spec.get("beliefs"),
                "style": persona_spec.get("speech_style", ""),
            })
            display_name = persona_spec.get("name")
            if display_name:
                person.define("name", display_name)
            self._persons[asset_id] = person
        return person

    @staticmethod
    def _summarize_state(visible_state: dict) -> str:
        return (
            f"第 {visible_state.get('tick', '?')} 回合。"
            f"地点：{visible_state.get('location', '未知')}。"
            f"{visible_state.get('recent_events', '')}"
        )

    @staticmethod
    def _map_action(action: dict) -> str | None:
        kind = {"TALK": "dialogue", "THINK": "inner_voice"}.get(action.get("type"))
        if action.get("type") == "DONE":
            return None
        return kind or "action"

    def reset_cost_stats(self) -> None:
        from tinytroupe.clients import client
        client().reset_cost_stats()

    def collect_total_tokens(self) -> int:
        from tinytroupe.clients import client
        return int(client().get_cost_stats().get("total_tokens", 0))

    def act(self, persona_spec: dict, visible_state: dict) -> dict:
        asset_id = visible_state.get("character_id") or persona_spec.get("name", "char_unknown")
        person = self._get_person(asset_id, persona_spec)
        person.listen(self._summarize_state(visible_state))

        last_error: Exception | None = None
        for _ in range(self._max_retries):
            try:
                results = person.act(return_actions=True) or []
                for item in results:
                    kind = self._map_action(item.get("action", {}))
                    if kind is None:
                        continue
                    emotions = item.get("cognitive_state", {}).get("emotions", "")
                    return {
                        "kind": kind,
                        "content": item["action"].get("content", ""),
                        "emotion": str(emotions),
                    }
                last_error = BackendActionError("本回合动作全部为 DONE")
            except Exception as e:  # LLM 结构漂移 / API 失败穿透
                last_error = e
        raise BackendActionError(
            f"角色 {asset_id} 动作解析重试 {self._max_retries} 次后仍失败: {last_error}"
        ) from last_error
