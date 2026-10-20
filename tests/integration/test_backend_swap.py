"""US3 接缝验证 1：角色后端可替换 —— 仅改注入参数，链路其余零改动。

覆盖 spec：FR-007 / SC-005；宪章原则 IV（适配器隔离）。
"""
import jsonschema

from db.init_db import init as init_db
from orchestrator.simulation import run_simulation
from orchestrator.store import Store

ASSET = {
    "asset_id": "char_swap_tester",
    "type": "character",
    "name": "替换测试员",
    "appearance": {"visual_prompt": "a swap-test character"},
    "persona_spec": {
        "age": 40, "occupation": "更夫", "personality": "木讷",
        "beliefs": "守夜即守心", "speech_style": "短句",
    },
    "provenance": {
        "researched_at": "2026-10-19T00:00:00+00:00", "retriever": "test",
        "model": "none", "confidence": 1.0,
    },
}

SCENE_ASSET = {
    "asset_id": "scene_swap_alley",
    "type": "scene",
    "name": "测试巷",
    "appearance": {"visual_prompt": "a narrow alley at night"},
    "provenance": {
        "researched_at": "2026-10-19T00:00:00+00:00", "retriever": "test",
        "model": "none", "confidence": 1.0,
    },
}


class AltMockBackend:
    """另一个 Mock 变体：满足 PersonaBackend Protocol 即可注入。"""

    def act(self, persona_spec: dict, visible_state: dict) -> list[dict]:
        return [{
            "kind": "dialogue",
            "content": f"{persona_spec.get('name', '角色')}：天干物燥，小心火烛。",
            "emotion": "平淡",
        }]


def test_backend_swap_requires_no_chain_changes(tmp_path):
    db = tmp_path / "swap.db"
    init_db(str(db))
    store = Store(str(db))
    try:
        store.put_asset(ASSET)
        store.put_asset(SCENE_ASSET)
        events = run_simulation(
            store, "swap_run", "world_swap",
            ["char_swap_tester"], "scene_swap_alley",
            ticks=4, backend=AltMockBackend(),
        )
    finally:
        store.close()

    assert len(events) == 5  # 1 scene_change + 4 ticks × 1 角色
    for ev in events:
        jsonschema.validate(ev, _event_schema())
    assert all(
        e["type"] == "dialogue" for e in events if e["tick"] >= 1
    ), "AltMockBackend 的动作应全部进入事件流"


def _event_schema() -> dict:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    return json.loads((root / "schemas" / "event.schema.json").read_text(encoding="utf-8"))
