"""WorldSeed 世界引擎适配器（宪章原则 II/IV 接缝）。

WorldSeed 的全部接触面集中在本模块（research.md R1/R6）：
- build_scene_config：资产库 → SceneConfig（角色卡含 secret + perception 规则 +
  机械效果动作集；DM 裁决为显式开关，dm=None 时输出与 006 版逐键一致）
- run_world：引擎驱动的世界循环（perceive → backend.act → submit → step），
  visible_state 由引擎感知派生（FR-003 单一真相源），契约事件 emit 复用 001 口径
- 快照：每 tick engine.save_state() → _CaptureRecorder → store.put_world_state；
  resume 时同配置重建引擎 + load_state，事件编号经 store.max_event_no() 连续
- DM 审计（010）：_CaptureRecorder 捕获引擎 dm_call 记录，run 结束落 dm_calls 表
"""
import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .dm import build_dm_knowledge, build_dm_provider
from .persona import PersonaBackend
from .simulation import _SHOT_BY_KIND  # 001 既定映射，逐字节复用
from .store import Store


class WorldConfigError(RuntimeError):
    """资产缺口或世界配置非法。"""


class WorldSnapshotError(RuntimeError):
    """快照损坏或版本不兼容。"""


@dataclass
class DMOptions:
    """真实裁决开关与参数。run_world/build_scene_config 传 None 即不启用。"""

    hint: str = "判定该动作在世界中的结果：成败、后果、对他人的可感知影响。"
    allowed_ops: list[str] = field(
        default_factory=lambda: ["set", "increment", "decrement", "emit_event"])
    max_effects: int = 5
    knowledge_chars: int = 2000
    max_calls: int = 50
    model: str = ""
    timeout_s: float = 30.0
    max_retries: int = 2

    def __post_init__(self):
        if not self.model:
            # 默认非思考模型：deepseek-flash 为思考模型，不支持裁决所需的
            # tool_choice（真机实测 010）
            self.model = os.environ.get("DM_MODEL", "deepseek-chat")


# 机械效果动作集（无 DM 段；say/whisper/act 口径照 teahouse.yaml 模板）
_ACTIONS = {
    "say": {
        "description": "大声说话。房间里的所有人都能听到。",
        "params": [{"name": "message", "type": "free_text", "required": True}],
        "preconditions": [],
        "effects": [],
        "events": [{"type": "say", "detail": "$agent 说: $message",
                    "ttl": 2, "scope": "same_location"}],
    },
    "whisper": {
        "description": "悄悄话。只有对方能听到。",
        "params": [
            {"name": "to", "type": "entity_ref", "required": True,
             "enum_from": "$visible", "enum_filter": {"type": "agent"}},
            {"name": "message", "type": "free_text", "required": True},
        ],
        "preconditions": [
            {"operator": "check", "left": "$to.location", "op": "==",
             "right": "$agent.location"},
        ],
        "effects": [],
        "events": [{"type": "whisper", "detail": "$agent 悄声对 $to 说: $message",
                    "ttl": 1, "scope": "target_only"}],
    },
    "act": {
        "description": "做一个公开动作（描述行为本身）。同房间的人都能看到。",
        "params": [{"name": "description", "type": "free_text", "required": True}],
        "preconditions": [],
        "effects": [],
        "events": [{"type": "act", "detail": "$agent $description",
                    "ttl": 2, "scope": "same_location"}],
    },
}

_PERCEPTION = {
    "visibility": [
        {"operator": "any", "conditions": [
            {"operator": "check", "left": "$observer.location", "op": "==",
             "right": "$entity.location"},
            {"operator": "check", "left": "$observer.location", "op": "==",
             "right": "$entity.id"},
        ]},
    ],
    "event_scopes": {
        "same_location": {
            "rules": [
                {"operator": "check", "left": "$observer.location", "op": "==",
                 "right": "$event_source.location"},
            ],
        },
    },
    "hidden_properties": ["secret", "goals"],
}


def build_scene_config(store: Store, character_ids: list[str],
                       location_id: str, dm: DMOptions | None = None) -> dict:
    """资产库 → SceneConfig 原始 dict（引擎 SceneConfig.model_validate 校验）。

    缺角色/缺场景时抛 WorldConfigError 并指出缺口（FR-001）。
    dm 非 None 时：act 动作挂裁决配置、scene 注入 dm_knowledge 与成本帽；
    dm=None 时输出与 006 版逐键一致（兼容锚点）。
    """
    if not character_ids:
        raise WorldConfigError("世界配置缺少角色资产（character_ids 为空）")
    try:
        scene_asset = store.get_asset(location_id)
    except KeyError as e:
        raise WorldConfigError(f"世界配置缺少场景资产: {e}") from e

    appearance = scene_asset.get("appearance", {})
    entities = [{
        "id": location_id,
        "type": "space",
        "description": appearance.get("description") or scene_asset["name"],
    }]

    agents = []
    for cid in character_ids:
        try:
            asset = store.get_asset(cid)
        except KeyError as e:
            raise WorldConfigError(f"世界配置缺少角色资产: {e}") from e
        spec = asset.get("persona_spec", {})
        beliefs = spec.get("beliefs", "")
        if isinstance(beliefs, list):
            beliefs = "；".join(str(b) for b in beliefs)
        personality = spec.get("personality", "")
        if isinstance(personality, list):
            personality = "、".join(str(p) for p in personality)
        agents.append({
            "id": cid,
            "location": location_id,
            "character": {
                "identity": f"{asset['name']}，{spec.get('occupation', '身份不详')}，"
                            f"{spec.get('age', '年龄不详')}。",
                "personality": str(personality) or "平平无奇",
                "goals": spec.get("goals", []),
                "secret": str(spec.get("secret") or beliefs or "没有特别的秘密"),
            },
        })

    config = {
        "scene": {"id": location_id,
                  "description": appearance.get("description") or scene_asset["name"]},
        "entities": entities,
        "agents": agents,
        "actions": _ACTIONS,
        "perception": _PERCEPTION,
        "auto_tick": [],
    }
    if dm is not None:
        config["actions"] = {
            **config["actions"],
            "act": {**config["actions"]["act"], "dm": {
                "hint": dm.hint,
                "allowed_ops": dm.allowed_ops,
                "max_effects": dm.max_effects,
            }},
        }
        config["scene"]["dm_knowledge"] = build_dm_knowledge(
            store, [*character_ids, location_id], dm.knowledge_chars)
        config["scene"]["max_dm_calls"] = dm.max_calls
    return config


class _CaptureRecorder:
    """捕获 engine.save_state() 的数据（引擎自带 NullRecorder 是无操作，
    RunRecorder 落 ~/.worldseed 不可配路径 —— research.md R4）。

    010 起同时捕获 dm_call 审计记录（引擎成功/失败路径都会 record）。"""

    def __init__(self):
        from worldseed.persistence import NullRecorder
        self._inner = NullRecorder()
        self.last_state: dict | None = None
        self.dm_calls: list[dict] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def record(self, kind: str, tick: int, **data):
        if kind == "dm_call":
            self.dm_calls.append({"tick": tick, **data})
        else:
            self._inner.record(kind, tick, **data)

    def save_state(self, entities, tick, **kwargs):
        self.last_state = {
            "entities": entities,
            "tick": tick,
            "characters": kwargs.get("characters", {}),
        }


def _make_engine(config: dict, dm_provider=None):
    from worldseed.models.config_schema import SceneConfig
    from worldseed.world import WorldEngine

    recorder = _CaptureRecorder()
    engine = WorldEngine(config=SceneConfig.model_validate(config),
                         recorder=recorder, dm_provider=dm_provider)
    engine.register_from_config()
    return engine, recorder


def _visible_state(perception, tick: int, character_id: str) -> dict:
    """AgentPerception → backend 既有 visible_state 键（接口零改动，R5）。"""
    self_state = perception.self_state or {}
    events = perception.events or []
    recent = "。".join(
        str(e.get("detail", "")) for e in events[-5:] if isinstance(e, dict)
    )
    return {
        "tick": tick,
        "location": self_state.get("location", ""),
        "character_id": character_id,
        "recent_events": recent,
    }


def _map_to_engine_action(action: dict) -> tuple[str, dict] | None:
    """backend 动作 → 引擎动作；inner_voice 只出契约事件、不进引擎。"""
    kind = action.get("kind")
    content = action.get("content", "")
    if not content.strip():
        return None
    if kind == "dialogue":
        return "say", {"message": content}
    if kind == "action":
        return "act", {"description": content}
    return None  # inner_voice / 未知


def _snapshot(engine, recorder: _CaptureRecorder, store: Store,
              world_id: str) -> None:
    engine.save_state()
    if recorder.last_state is None:
        raise WorldSnapshotError("引擎 save_state 未产出快照数据")
    store.put_world_state(world_id, recorder.last_state["tick"],
                          json.dumps(recorder.last_state, ensure_ascii=False))


def run_world(store: Store, run_id: str, world_id: str,
              character_ids: list[str], location_id: str, ticks: int,
              backend: PersonaBackend, resume: bool = False,
              dm: DMOptions | None = None,
              dm_provider=None) -> list[dict]:
    """引擎驱动的世界循环；resume=True 时从 worlds.state 最近快照续跑。

    dm 非 None 时启用真实裁决（dm_provider 为 None 则经 build_dm_provider
    构造；测试可注入 MockDMProvider）；run 结束后 dm_call 审计落库。
    """
    if dm is not None and dm_provider is None:
        dm_provider = build_dm_provider(dm)
    config = build_scene_config(store, character_ids, location_id, dm=dm)
    engine, recorder = _make_engine(config, dm_provider=dm_provider)

    start_tick = 1
    if resume:
        saved = store.get_world_state(world_id)
        if saved is None:
            raise WorldSnapshotError(f"world {world_id} 无可续跑快照")
        snap_tick, state_json = saved
        try:
            state = json.loads(state_json)
            engine.load_state(state["entities"], state["tick"],
                              characters=state.get("characters"))
        except (ValueError, KeyError, TypeError) as e:
            raise WorldSnapshotError(f"快照损坏，无法续跑: {e}") from e
        start_tick = snap_tick + 1

    store.create_run(run_id, world_id)

    personas = []
    for cid in character_ids:
        asset = store.get_asset(cid)
        personas.append((cid, dict(asset.get("persona_spec", {}),
                                   name=asset["name"])))

    events: list[dict] = []
    seq_no = store.max_event_no()
    prev_event_by_char: dict[str, str] = {}

    def emit(tick: int, seq: int, etype: str, content: str,
             chars: list[str], emotion: str = "",
             cause: list[str] | None = None) -> dict:
        nonlocal seq_no
        seq_no += 1
        event = {
            "event_id": f"e{seq_no:04d}",
            "run_id": run_id,
            "tick": tick,
            "seq": seq,
            "type": etype,
            "characters": chars,
            "location": location_id,
            "content": content,
            "emotion": emotion,
            "cause_refs": cause or [],
            "shot_hint": _SHOT_BY_KIND.get(
                etype, {"camera": "medium", "duration_s": 3.0}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        store.put_event(event)
        events.append(event)
        return event

    if not resume:
        scene_asset = store.get_asset(location_id)
        visual = scene_asset.get("appearance", {}).get("visual_prompt", "")
        emit(0, 0, "scene_change",
             f"场景：{scene_asset['name']}。{visual}", character_ids)

    end_tick = start_tick + ticks - 1
    for tick in range(start_tick, end_tick + 1):
        seq = 0
        for cid, spec in personas:
            perception = engine.perceive(cid)
            actions = backend.act(spec, _visible_state(perception, tick, cid))
            for action in actions:
                seq += 1
                engine_action = _map_to_engine_action(action)
                if engine_action is not None:
                    verb, params = engine_action
                    engine.submit(cid, verb, params)
                emitted = emit(
                    tick, seq, action["kind"], action["content"], [cid],
                    action.get("emotion", ""),
                    [prev_event_by_char[cid]] if cid in prev_event_by_char else [],
                )
                prev_event_by_char[cid] = emitted["event_id"]
        if dm_provider is not None:
            asyncio.run(engine.step_async())
        else:
            engine.step()
        _snapshot(engine, recorder, store, world_id)

    for rec in recorder.dm_calls:
        store.put_dm_call(
            run_id, rec["tick"], rec.get("action", ""),
            rec.get("agent_id", ""),
            json.dumps(rec.get("params", {}), ensure_ascii=False),
            rec.get("hint", ""), rec.get("narrative", ""),
            json.dumps(rec.get("effects", []), ensure_ascii=False),
            rec.get("tokens_in", 0), rec.get("tokens_out", 0),
            rec.get("elapsed_s", 0.0), bool(rec.get("failed", False)),
        )

    store.finish_run(run_id, "done")
    return events
