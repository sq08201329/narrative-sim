"""CLI 与 MCP 共用的叙事工作流。"""
import contextlib
import json
import sys
from pathlib import Path

from db.init_db import init as init_db
from .persona import MockPersonaBackend
from .research import research_asset as _research_asset
from .simulation import export_jsonl as _export_jsonl
from .store import Store
from .world import build_scene_config as _build_scene_config
from .world import run_world as _run_world


class WorldExists(RuntimeError):
    pass


class WorldNotFound(RuntimeError):
    pass


class RunNotFound(RuntimeError):
    pass


def _open_store(db_path: str) -> Store:
    init_db(db_path)
    return Store(db_path)


def research(db_path: str, query: str, asset_type: str, *, research_fn=None) -> dict:
    store = _open_store(db_path)
    try:
        before = len(store.list_assets(asset_type))
        run = research_fn or _research_asset
        asset_id = run(query, asset_type, store)
        after = len(store.list_assets(asset_type))
        return {"asset_id": asset_id, "deduplicated": after == before}
    finally:
        store.close()


def create_world(db_path: str, world_id: str, character_ids: list[str],
                 location_id: str, reset: bool = False,
                 memory_from: str | None = None) -> dict:
    store = _open_store(db_path)
    try:
        if store.get_world_config(world_id) is not None and not reset:
            raise WorldExists(f"world {world_id} 已存在（reset=True 可覆盖）")
        cfg = _build_scene_config(store, character_ids, location_id)
        for asset_id in [*character_ids, location_id]:
            store.ensure_revision0(asset_id)
        pins = {asset_id: store.current_revision(asset_id)
                for asset_id in [*character_ids, location_id]}
        store.put_world_config(world_id, json.dumps(
            {"character_ids": character_ids, "location_id": location_id,
             "revisions": pins, "memory_from": memory_from},
            ensure_ascii=False))
        return {"world_id": world_id, "characters": character_ids,
                "location": location_id, "action_count": len(cfg["actions"]),
                "revision_pins": pins, "memory_from": memory_from}
    finally:
        store.close()


def run_simulation(db_path: str, world_id: str, run_id: str, ticks: int,
                   backend: str = "tinytroupe", resume: bool = False,
                   dm: bool = False, dm_max_calls: int = 50,
                   dm_knowledge_chars: int = 2000,
                   memory_from: str | None = None) -> dict:
    store = _open_store(db_path)
    try:
        cfg = store.get_world_config(world_id)
        if cfg is None:
            raise WorldNotFound(f"world {world_id} 不存在（先 create_world）")
        if backend == "mock":
            persona_backend = MockPersonaBackend()
            tokens = None
        else:
            from .persona_tinytroupe import TinyTroupeBackend
            persona_backend = TinyTroupeBackend()
            persona_backend.reset_cost_stats()
        dm_options = None
        if dm:
            from .world import DMOptions
            dm_options = DMOptions(knowledge_chars=dm_knowledge_chars,
                                   max_calls=dm_max_calls)
        with contextlib.redirect_stdout(sys.stderr):
            events = _run_world(store, run_id, world_id, cfg["character_ids"],
                                cfg["location_id"], ticks, persona_backend,
                                resume=resume, dm=dm_options,
                                pins=cfg.get("revisions"),
                                memory_from=memory_from or cfg.get("memory_from"))
        cost = None
        if backend != "mock":
            cost = persona_backend.collect_total_tokens()
            store.update_run_cost(run_id, cost)
        result = {"run_id": run_id, "event_count": len(events),
                  "ticks": ticks, "cost_tokens": cost}
        if dm:
            calls = store.list_dm_calls(run_id)
            result["dm_calls"] = len(calls)
            result["dm_failed"] = sum(1 for call in calls if call["failed"])
        return result
    finally:
        store.close()


def export_events(db_path: str, run_id: str, out_path: str) -> dict:
    store = _open_store(db_path)
    try:
        if not store.run_exists(run_id):
            raise RunNotFound(f"run {run_id} 不存在")
        count = len(store.export_events(run_id))
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        path = _export_jsonl(store, run_id, out_path)
        return {"path": path, "count": count}
    finally:
        store.close()
