"""M1 最小链路验收：资产入库 → 4 回合仿真 → 导出事件 JSONL → 逐条复验。

用法（仓库根目录）：
    uv run python scripts/run_minimal_chain.py [--db PATH] [--out PATH] [--run-id ID]

全程离线，无需任何密钥（Mock 角色后端）。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.init_db import init as init_db  # noqa: E402
from orchestrator.persona import MockPersonaBackend  # noqa: E402
from orchestrator.simulation import export_jsonl, run_simulation  # noqa: E402
from orchestrator.store import Store  # noqa: E402

CHARACTER = {
    "asset_id": "char_su_wanqing",
    "type": "character",
    "name": "苏晚晴",
    "appearance": {
        "visual_prompt": "A 24-year-old Chinese female physician in late Song dynasty, "
                         "plain indigo robe, hair pinned with a wooden hairpin, "
                         "carrying a bamboo medicine chest",
        "description": "二十四岁，靛青布衫，木簪束发，背负竹药箱",
        "attire": "靛青布衫，袖口磨白",
    },
    "persona_spec": {
        "age": 24,
        "occupation": "游方医者",
        "personality": "外冷内热，谨慎多疑",
        "beliefs": "医者不问出身，只问伤病",
        "speech_style": "简短克制，偶用医理打比方",
    },
    "historical_context": {
        "epoch": "南宋末年",
        "region": "临安府",
        "sources": [],
    },
    "reference_images": [],
    "provenance": {
        "researched_at": "2026-10-19T00:00:00+00:00",
        "retriever": "manual",
        "model": "none",
        "confidence": 1.0,
    },
    "status": "draft",
}

SCENE = {
    "asset_id": "scene_yanyu_teahouse",
    "type": "scene",
    "name": "烟雨茶楼",
    "appearance": {
        "visual_prompt": "A two-story wooden teahouse by the river in Southern Song China, "
                         "rainy dusk, lanterns glowing, sparse patrons",
        "description": "临河两层木楼，雨天黄昏，灯笼微亮，茶客稀疏",
    },
    "historical_context": {"epoch": "南宋末年", "region": "临安府", "sources": []},
    "reference_images": [],
    "provenance": {
        "researched_at": "2026-10-19T00:00:00+00:00",
        "retriever": "manual",
        "model": "none",
        "confidence": 1.0,
    },
    "status": "draft",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="M1 最小仿真链路")
    parser.add_argument("--db", default="narrative_sim.db")
    parser.add_argument("--out", default=str(ROOT / "exports" / "m1_events.jsonl"))
    parser.add_argument("--run-id", default="m1_run")
    args = parser.parse_args()

    init_db(args.db)
    store = Store(args.db)
    try:
        if store.run_exists(args.run_id):
            print(f"运行 {args.run_id} 已存在，显式重置后重跑")
            store.reset_run(args.run_id)

        store.put_asset(CHARACTER)
        store.put_asset(SCENE)
        print("资产入库：char_su_wanqing, scene_yanyu_teahouse")

        events = run_simulation(
            store, args.run_id, "world_m1",
            ["char_su_wanqing"], "scene_yanyu_teahouse",
            ticks=4, backend=MockPersonaBackend(),
        )
        print(f"仿真完成: {len(events)} 个事件")

        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        export_jsonl(store, args.run_id, args.out)
        validated = store.export_events(args.run_id)  # 导出路径逐条复验契约
        print(f"导出 {args.out}，复验 {len(validated)} 条全部通过契约校验")
    finally:
        store.close()

    print("验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
