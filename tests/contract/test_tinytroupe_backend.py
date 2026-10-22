"""US1 单元测试：TinyTroupeBackend 动作映射 / 实例缓存 / 环境预检 / 终极失败。

全程离线：用 FakeTinyPerson 替换真实 TinyPerson（plan D9）。
先写测试，确认 FAIL 后实现 orchestrator/persona_tinytroupe.py。
"""
import pytest

from orchestrator.persona_tinytroupe import (
    BackendActionError,
    MissingEnvironmentError,
    TinyTroupeBackend,
)


class FakeTinyPerson:
    """模拟 TinyPerson 的最小接口：build 计数 + 剧本化 act 返回。"""

    build_count = 0
    scripted_actions: list[dict] = []
    fail_times = 0

    def __init__(self, name):
        type(self).build_count += 1
        self.name = name
        self.persona = None

    def include_persona_definitions(self, definitions):
        self.persona = definitions

    def define(self, key, value, **kwargs):
        self.persona[key] = value

    def listen(self, text, **kwargs):
        self.last_heard = text

    def act(self, return_actions=False, **kwargs):
        if type(self).fail_times > 0:
            type(self).fail_times -= 1
            raise TypeError("LLM 响应为空")
        return [
            {"action": a, "cognitive_state": {"emotions": "平静而警觉"}}
            for a in type(self).scripted_actions
        ]


@pytest.fixture()
def backend(monkeypatch):
    FakeTinyPerson.build_count = 0
    FakeTinyPerson.scripted_actions = []
    FakeTinyPerson.fail_times = 0
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    b = TinyTroupeBackend(person_cls=FakeTinyPerson)
    return b


PERSONA = {
    "name": "苏晚晴", "age": 24, "occupation": "游方医者",
    "personality": "外冷内热", "beliefs": "医者不问出身", "speech_style": "简短克制",
}
STATE = {"tick": 1, "location": "scene_yanyu_teahouse", "character_id": "char_su_wanqing"}


def test_talk_maps_to_dialogue(backend):
    FakeTinyPerson.scripted_actions = [{"type": "TALK", "content": "在下初到贵地。", "target": None}]
    out = backend.act(PERSONA, STATE)
    assert out == [{"kind": "dialogue", "content": "在下初到贵地。", "emotion": "平静而警觉"}]


def test_think_maps_to_inner_voice(backend):
    FakeTinyPerson.scripted_actions = [{"type": "THINK", "content": "此处不宜久留。", "target": None}]
    assert backend.act(PERSONA, STATE)[0]["kind"] == "inner_voice"


def test_done_is_skipped(backend):
    FakeTinyPerson.scripted_actions = [
        {"type": "DONE", "content": "", "target": None},
        {"type": "TALK", "content": "告辞。", "target": None},
    ]
    assert backend.act(PERSONA, STATE)[0]["content"] == "告辞。"


def test_person_cached_by_asset_id(backend):
    FakeTinyPerson.scripted_actions = [{"type": "TALK", "content": "嗯。", "target": None}]
    backend.act(PERSONA, STATE)
    backend.act(PERSONA, dict(STATE, tick=2))
    assert FakeTinyPerson.build_count == 1


def test_speech_style_maps_to_style(backend):
    FakeTinyPerson.scripted_actions = [{"type": "TALK", "content": "嗯。", "target": None}]
    backend.act(PERSONA, STATE)
    person = backend._persons["char_su_wanqing"]
    assert person.persona["style"] == "简短克制"
    assert person.persona["occupation"] == "游方医者"


def test_missing_api_key_raises(monkeypatch):
    # 隔离 .env（项目根现有真实 key 的 .env，load_dotenv 会回填）
    monkeypatch.setattr("orchestrator.persona_tinytroupe.load_dotenv",
                        lambda: None)
    for var in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    with pytest.raises(MissingEnvironmentError, match="OPENAI_API_KEY"):
        TinyTroupeBackend(person_cls=FakeTinyPerson)


def test_missing_base_url_raises(monkeypatch):
    monkeypatch.setattr("orchestrator.persona_tinytroupe.load_dotenv",
                        lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    for var in ("OPENAI_BASE_URL", "DEEPSEEK_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(MissingEnvironmentError, match="OPENAI_BASE_URL"):
        TinyTroupeBackend(person_cls=FakeTinyPerson)


def test_deepseek_key_bridges_to_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-bridge")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid")
    import os
    TinyTroupeBackend(person_cls=FakeTinyPerson)
    assert os.environ["OPENAI_API_KEY"] == "sk-bridge"


def test_ultimate_failure_raises_and_emits_nothing(backend):
    FakeTinyPerson.fail_times = 5
    with pytest.raises(BackendActionError, match="重试"):
        backend.act(PERSONA, STATE)


def test_full_action_sequence_collected_in_order(backend):
    """008 修复回归：一次 act() 的 THINK→TALK→DONE 序列必须全部保留
    （002 版只取第一个，TALK 被系统性丢弃——"角色从不开口"的根因）。"""
    FakeTinyPerson.scripted_actions = [
        {"type": "THINK", "content": "先想清楚。", "target": None},
        {"type": "TALK", "content": "再开口说。", "target": None},
        {"type": "DONE", "content": "", "target": None},
    ]
    out = backend.act(PERSONA, STATE)
    assert [a["kind"] for a in out] == ["inner_voice", "dialogue"]
    assert [a["content"] for a in out] == ["先想清楚。", "再开口说。"]
