"""最小仿真循环与事件导出（M1：Mock 驱动的占位世界）。

事件契约要点：run_id → tick → seq 排序；characters 只引用 asset_id；
cause_refs 链接同一角色的上一事件，供剧情回溯。
"""
import json
from datetime import datetime, timezone

from .persona import PersonaBackend
from .store import Store

_SHOT_BY_KIND = {
    "dialogue": {"camera": "medium", "duration_s": 4.0},
    "action": {"camera": "wide", "duration_s": 3.0},
    "inner_voice": {"camera": "close_up", "duration_s": 2.5},
    "scene_change": {"camera": "wide", "duration_s": 3.0},
    "narration": {"camera": "pan", "duration_s": 3.0},
}


def run_simulation(
    store: Store,
    run_id: str,
    world_id: str,
    character_ids: list[str],
    location_id: str,
    ticks: int,
    backend: PersonaBackend,
) -> list[dict]:
    store.create_run(run_id, world_id)

    personas = []
    for cid in character_ids:
        asset = store.get_asset(cid)
        personas.append((cid, dict(asset.get("persona_spec", {}), name=asset["name"])))

    events: list[dict] = []
    seq_no = 0
    prev_event_by_char: dict[str, str] = {}

    def emit(tick: int, seq: int, etype: str, content: str,
             chars: list[str], emotion: str = "", cause: list[str] | None = None) -> dict:
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
            "shot_hint": _SHOT_BY_KIND.get(etype, {"camera": "medium", "duration_s": 3.0}),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        store.put_event(event)
        events.append(event)
        return event

    scene = store.get_asset(location_id)
    visual = scene.get("appearance", {}).get("visual_prompt", "")
    emit(0, 0, "scene_change", f"场景：{scene['name']}。{visual}", character_ids)

    for tick in range(1, ticks + 1):
        for seq, (cid, spec) in enumerate(personas, start=1):
            action = backend.act(spec, {"tick": tick, "location": location_id})
            emitted = emit(
                tick, seq, action["kind"], action["content"], [cid],
                action.get("emotion", ""),
                [prev_event_by_char[cid]] if cid in prev_event_by_char else [],
            )
            prev_event_by_char[cid] = emitted["event_id"]

    store.finish_run(run_id, "done")
    return events


def export_jsonl(store: Store, run_id: str, out_path: str) -> str:
    """按 tick/seq 导出事件流；导出前 store 已逐条复验契约。"""
    events = store.export_events(run_id)
    with open(out_path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return out_path
