"""TinyTroupe 真后端：PersonaBackend Protocol 的在线实现（宪章原则 II/IV 接缝）。

所有 TinyTroupe 接触面集中在本文件：
- 环境预检后才懒 import tinytroupe（其 import 即实例化 embedding 客户端，缺 key 会炸）
- OPENAI_API_KEY / OPENAI_BASE_URL 是 openai SDK 原生读取的变量，由 .env 提供；
  仅有 DEEPSEEK_* 时桥接映射
- TinyPerson 实例按 asset_id 缓存（全局注册表重名即报错，实例名直接用 asset_id）
- 动作映射：TALK→dialogue、THINK→inner_voice、DONE 丢弃；emotion 取 cognitive_state
"""
import os

from dotenv import load_dotenv

from .persona import PersonaBackend

MAX_ACT_RETRIES = 3


class MissingEnvironmentError(RuntimeError):
    """真后端所需环境变量缺失。"""


class BackendActionError(RuntimeError):
    """动作解析重试耗尽后的终极失败。"""


class TinyTroupeBackend(PersonaBackend):
    def __init__(self, person_cls=None, max_retries: int = MAX_ACT_RETRIES):
        load_dotenv()
        self._bridge_deepseek_env()
        for var in ("OPENAI_API_KEY", "OPENAI_BASE_URL"):
            if not os.environ.get(var):
                raise MissingEnvironmentError(
                    f"缺少环境变量 {var}：请在 .env 中配置（或设置 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL）"
                )
        self._person_cls = person_cls
        self._persons: dict[str, object] = {}
        self._max_retries = max_retries

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

    def _get_person(self, asset_id: str, persona_spec: dict):
        person = self._persons.get(asset_id)
        if person is None:
            person = self._person_class()(name=asset_id)
            person.include_persona_definitions({
                "name": persona_spec.get("name", asset_id),
                "age": persona_spec.get("age"),
                "occupation": persona_spec.get("occupation"),
                "personality": persona_spec.get("personality"),
                "beliefs": persona_spec.get("beliefs"),
                "style": persona_spec.get("speech_style", ""),
            })
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
