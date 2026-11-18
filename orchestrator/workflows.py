"""CLI 与 MCP 共用的叙事工作流。"""
import contextlib
import json
import sys
from pathlib import Path

from db.init_db import init as init_db
from . import story_tree as _story_tree
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


class TreeNotFound(RuntimeError):
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


def _create_world_in_store(store: Store, world_id: str,
                           character_ids: list[str], location_id: str,
                           reset: bool = False,
                           memory_from: str | None = None) -> dict:
    """建世界的单一实现；create_world 与 timeline drive 共用（宪章 II）。"""
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


def create_world(db_path: str, world_id: str, character_ids: list[str],
                 location_id: str, reset: bool = False,
                 memory_from: str | None = None) -> dict:
    store = _open_store(db_path)
    try:
        return _create_world_in_store(store, world_id, character_ids,
                                      location_id, reset=reset,
                                      memory_from=memory_from)
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


# ---- 故事时间树（023）----

def import_timeline(db_path: str, tree_id: str, text: str,
                    *, overwrite: bool = False,
                    chat_json_fn=None) -> dict:
    """抽取纯文本 → 客观自查 → 通过后入库；失败不写库（FR-004/006/008）。"""
    tree = _story_tree.parse_story(text, tree_id, chat_json_fn=chat_json_fn)
    store = _open_store(db_path)
    try:
        store.put_tree(tree, overwrite=overwrite)
    finally:
        store.close()
    return {"tree_id": tree_id, "status": tree["status"],
            "node_count": len(tree["nodes"]),
            "checks": tree["self_check"]["checks"]}


def show_timeline(db_path: str, tree_id: str) -> dict:
    store = _open_store(db_path)
    try:
        tree = store.get_tree(tree_id)
        if tree is None:
            raise TreeNotFound(f"时间树不存在: {tree_id}")
        return tree
    finally:
        store.close()


def export_timeline(db_path: str, tree_id: str, out_path: str) -> dict:
    tree = show_timeline(db_path, tree_id)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(tree, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    return {"path": out_path, "tree_id": tree_id, "node_count": len(tree["nodes"])}


def _backend_for(backend: str):
    if backend == "mock":
        return MockPersonaBackend(), None
    from .persona_tinytroupe import TinyTroupeBackend
    b = TinyTroupeBackend()
    b.reset_cost_stats()
    return b, b


def _require_ready(tree: dict) -> None:
    """ready 门槛：自查未通过一律拒绝，不产生副作用（FR-009）。"""
    if tree.get("status") != "ready" or tree.get("self_check", {}).get("passed") is not True:
        raise _story_tree.TreeError("时间树未就绪（自查未通过），禁止 drive")


def drive_timeline(db_path: str, tree_id: str, stage: str, *,
                   world_id: str | None = None,
                   run_id: str | None = None,
                   ticks: int | None = None,
                   backend: str = "tinytroupe",
                   research_asset_fn=None) -> dict:
    """按时间树分阶段推进：research → world → run。每阶段先校验 ready。"""
    if stage not in {"research", "world", "run"}:
        raise ValueError(f"未知 stage: {stage}（research/world/run）")
    store = _open_store(db_path)
    try:
        tree = store.get_tree(tree_id)
        if tree is None:
            raise TreeNotFound(f"时间树不存在: {tree_id}")
        _require_ready(tree)

        if stage == "research":
            from . import brief as brief_mod
            ledger = brief_mod.execute_brief(
                _story_tree.build_research_brief(tree), store,
                research_asset_fn=research_asset_fn)
            tree["entity_assets"] = _story_tree.resolve_entity_assets(tree, ledger)
            store.put_tree(tree, overwrite=True)
            return {"stage": stage, "tree_id": tree_id, "ledger": ledger,
                    "entity_assets": tree["entity_assets"]}

        if stage == "world":
            if not world_id:
                raise ValueError("world 阶段需要 --world-id")
            assets = tree.get("entity_assets") or {}
            specs = _story_tree.build_world_specs(tree, assets, world_id)
            worlds = [_create_world_in_store(
                store, s["world_id"], s["character_ids"], s["location_id"])
                for s in specs]
            tree["node_worlds"] = {
                nid: s["world_id"] for s in specs for nid in s["node_ids"]}
            store.put_tree(tree, overwrite=True)
            return {"stage": stage, "tree_id": tree_id, "worlds": worlds,
                    "node_worlds": tree["node_worlds"]}

        # stage == "run"
        if not run_id:
            raise ValueError("run 阶段需要 --run-id")
        node_worlds = tree.get("node_worlds") or {}
        if not node_worlds:
            raise ValueError("尚未建世界（先 drive --stage world）")
        groups: dict[str, list[dict]] = {}
        for node in store.list_tree_nodes(tree_id):
            wid = node_worlds.get(node["node_id"])
            if wid:
                groups.setdefault(wid, []).append(node)
        backend_obj, cost_obj = _backend_for(backend)
        runs = []
        run_nodes = {}
        for wid, nodes in groups.items():
            cfg = store.get_world_config(wid)
            n_ticks = ticks or len(nodes)
            mapping = _story_tree.map_nodes_to_ticks(nodes, n_ticks)
            rid = run_id if len(groups) == 1 else f"{run_id}__{nodes[0]['node_id']}"
            with contextlib.redirect_stdout(sys.stderr):
                events = _run_world(
                    store, rid, wid, cfg["character_ids"], cfg["location_id"],
                    n_ticks, backend_obj, pins=cfg.get("revisions"),
                    tick_to_node=mapping)
            cost = None
            if cost_obj is not None:
                cost = cost_obj.collect_total_tokens()
                store.update_run_cost(rid, cost)
            runs.append({"run_id": rid, "world_id": wid,
                         "event_count": len(events), "ticks": n_ticks,
                         "cost_tokens": cost})
            run_nodes[rid] = [n["node_id"] for n in nodes]
        tree["run_nodes"] = run_nodes
        store.put_tree(tree, overwrite=True)
        return {"stage": stage, "tree_id": tree_id, "runs": runs}
    finally:
        store.close()
