"""预演数据导出：run_id 的事件流 + 资产 → previz_data.js（Three.js 预演器消费）。

用法：uv run python scripts/export_previz.py --run-id world_r1 [--db world_real.db]
      [--out previz/previz_data.js]
产出 window.PREVIZ_DATA，供 previz/index.html 直接 file:// 打开（无 CORS 问题）。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orchestrator.store import Store  # noqa: E402

# 每角色固定配色（预演占位用，与创作无关）
_PALETTE = ["#4a90d9", "#d97a4a", "#5cb85c", "#b85cd9", "#d9b44a", "#4ad9c8"]


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 Three.js 预演数据")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db", default="data/narrative_sim.db")
    parser.add_argument("--out", default=str(ROOT / "previz" / "previz_data.js"))
    args = parser.parse_args()

    store = Store(args.db)
    try:
        events = store.export_events(args.run_id)
        if not events:
            print(f"run {args.run_id} 无事件", file=sys.stderr)
            return 1

        char_ids = sorted({c for e in events for c in e["characters"]})
        characters = []
        for i, cid in enumerate(char_ids):
            try:
                asset = store.get_asset(cid)
                characters.append({
                    "asset_id": cid,
                    "name": asset["name"],
                    "description": asset.get("appearance", {}).get("description", ""),
                    "visual_prompt": asset.get("appearance", {}).get("visual_prompt", ""),
                    "color": _PALETTE[i % len(_PALETTE)],
                    "slot": i,
                })
            except KeyError:
                continue

        scene_id = next((e["location"] for e in events if e.get("location")), None)
        scene = None
        if scene_id:
            try:
                sa = store.get_asset(scene_id)
                scene = {"asset_id": scene_id, "name": sa["name"],
                         "description": sa.get("appearance", {}).get("description", ""),
                         "visual_prompt": sa.get("appearance", {}).get("visual_prompt", "")}
            except KeyError:
                pass

        data = {
            "title": args.run_id,
            "scene": scene,
            "characters": characters,
            "events": [{
                "event_id": e["event_id"],
                "tick": e["tick"],
                "seq": e["seq"],
                "type": e["type"],
                "characters": e["characters"],
                "content": e["content"],
                "emotion": e.get("emotion", ""),
                "duration_s": e.get("shot_hint", {}).get("duration_s", 3.0),
                "camera": e.get("shot_hint", {}).get("camera", "medium"),
            } for e in events],
        }
    finally:
        store.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "window.PREVIZ_DATA = "
        + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8")
    print(f"预演数据导出: {out}（{len(data['events'])} 事件 / "
          f"{len(characters)} 角色）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
