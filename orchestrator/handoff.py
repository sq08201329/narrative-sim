"""素材移交包导出（011 US3，宪章 II 胶水层）。

产出 <out_dir>/<world_id>/ 自描述目录：manifest.json（sha256/计数/版号锚点/
密级说明）+ assets/ + events.jsonl + world.json + dm_calls.json +
materials/ + sources.md。全部为 store 既有读方法的组合，零新存储路径。
"""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .store import Store

FORMAT = "narrative-sim-handoff/1"

_SECRECY = ("assets/*/persona_spec.secret 与 world.json 中的 secret "
            "为创作可见、仿真角色不可见信息；移交下游时请勿回灌仿真角色视野")


class HandoffExists(RuntimeError):
    """移交目录已存在且未显式允许覆盖。"""


def _write(path: Path, content: str, items: list[dict],
           root: Path, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    items.append({
        "path": str(path.relative_to(root)),
        "kind": kind,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    })


def export_handoff(store: Store, world_id: str, out_dir: str,
                   run_id: str | None = None,
                   overwrite: bool = False,
                   include_images: bool = False) -> dict:
    """导出移交包。run_id 缺省取该世界最近 run；无 run 时事件/裁决为空集。
    include_images=True 才带本系统生成的参考图——默认不带：自产图为
    内部草稿，创作部门以 visual_prompt 为准用专业通道重做（013 定位）。"""
    cfg_row = store.get_world_config(world_id)
    if cfg_row is None:
        raise KeyError(f"世界不存在: {world_id}")
    pins = cfg_row.get("revisions") or {}
    character_ids = cfg_row.get("character_ids", [])
    location_id = cfg_row.get("location_id", "")

    if run_id is None:
        runs = store.list_runs(world_id)
        run_id = runs[-1] if runs else None

    target = Path(out_dir) / world_id
    if target.exists():
        if not overwrite:
            raise HandoffExists(
                f"移交目录已存在: {target}（overwrite=True 可覆盖）")
        shutil.rmtree(target)
    target.mkdir(parents=True)

    items: list[dict] = []

    # 资产（含 secret + 密级标注）
    asset_ids = [*character_ids, location_id]
    for aid in asset_ids:
        asset = store.get_asset(aid)
        asset["current_revision"] = store.current_revision(aid)
        asset["secrecy"] = ("persona_spec.secret：创作可见，"
                            "仿真中其他角色不可见")
        _write(target / "assets" / f"{aid}.json",
               json.dumps(asset, ensure_ascii=False, indent=2),
               items, target, "asset")

    # 事件流 / 世界快照 / 裁决台账
    events = store.export_events(run_id) if run_id else []
    _write(target / "events.jsonl",
           "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
           items, target, "events")
    saved = store.get_world_state(world_id)
    world_state = {"tick": saved[0], "state": json.loads(saved[1])} \
        if saved else {"tick": None, "state": None}
    _write(target / "world.json",
           json.dumps(world_state, ensure_ascii=False, indent=2),
           items, target, "world_state")
    dm_calls = store.list_dm_calls(run_id) if run_id else []
    _write(target / "dm_calls.json",
           json.dumps(dm_calls, ensure_ascii=False, indent=2),
           items, target, "dm_calls")

    # 调研原料（每资产一个 md）
    material_count = 0
    for aid in asset_ids:
        mats = store.get_materials(aid)
        if not mats:
            continue
        material_count += len(mats)
        md = "\n\n".join(
            f"## 【{m['query']}】\n\n来源检索器：{m['retriever']}｜"
            f"时间：{m['created_at']}\n\n{m['context']}" for m in mats)
        _write(target / "materials" / f"{aid}.md",
               f"# {aid} 调研原料\n\n{md}\n", items, target, "materials")

    # 参考图（013）：默认不带（自产图为内部草稿）；显式 include_images 才复制
    image_count = 0
    for aid in asset_ids if include_images else []:
        asset = store.get_asset(aid)
        for ref in asset.get("reference_images") or []:
            src = Path(ref)
            if not src.exists():
                continue
            dest = target / "images" / aid / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            items.append({
                "path": str(dest.relative_to(target)),
                "kind": "image",
                "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                "bytes": dest.stat().st_size,
            })
            image_count += 1

    # 溯源汇总
    lines = ["# 溯源汇总\n"]
    for aid in asset_ids:
        asset = store.get_asset(aid)
        prov = asset.get("provenance", {})
        lines.append(f"- **{aid}**（{asset.get('name', '')}）："
                     f"retriever={prov.get('researched_at', '')} "
                     f"{prov.get('retriever', '')} "
                     f"model={prov.get('model', '')} "
                     f"confidence={prov.get('confidence', '')}")
        for m in store.get_materials(aid):
            lines.append(f"  - 原料「{m['query']}」via {m['retriever']}")
    _write(target / "sources.md", "\n".join(lines) + "\n",
           items, target, "sources")

    counts = {"assets": len(asset_ids), "events": len(events),
              "dm_calls": len(dm_calls), "materials": material_count,
              "images": image_count}
    manifest = {
        "format": FORMAT,
        "world_id": world_id,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "revision_pins": pins,
        "items": items,
        "secrecy": _SECRECY,
        "counts": counts,
    }
    _write(target / "manifest.json",
           json.dumps(manifest, ensure_ascii=False, indent=2),
           items, target, "manifest")
    # manifest 写入后 items 里多了 manifest 自身一行——重写一次使其自洽
    manifest["items"] = items[:-1]
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"dir": str(target), "manifest": manifest, "counts": counts}
