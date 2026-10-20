"""M4 世界链路：WorldSeed 引擎驱动 + TinyTroupe 角色后端。

用法（cwd 必须是项目根目录，TinyTroupe 读 ./config.ini）：
    uv run python scripts/run_world_chain.py [--db PATH] [--world-id ID]
        [--run-id ID] [--ticks N] [--resume] [--mock]

--resume 从 worlds.state 最近快照续跑；--mock 用 MockPersonaBackend（离线冒烟）。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from db.init_db import init as init_db  # noqa: E402
from orchestrator.simulation import export_jsonl  # noqa: E402
from orchestrator.store import Store  # noqa: E402
from orchestrator.world import run_world  # noqa: E402
from run_minimal_chain import CHARACTER, SCENE  # noqa: E402

CHARACTER_2 = {
    "asset_id": "char_shen_ke",
    "type": "character",
    "name": "沈刻",
    "appearance": {
        "visual_prompt": "A 40-year-old Chinese silk merchant in late Song dynasty, "
                         "dark brown robe, abacus ring, sharp evaluating gaze",
        "description": "四十岁，褐色绸衫，多疑健谈的丝绸商人",
    },
    "persona_spec": {
        "age": 40,
        "occupation": "丝绸商人",
        "personality": "健谈、多疑、有条理",
        "beliefs": "无事不登三宝殿，人人皆有图谋",
        "speech_style": "热情寒暄中藏着试探",
        "secret": "他是缉捕司的暗桩，正在追查城中的密探网络",
    },
    "historical_context": {"epoch": "南宋末年", "region": "临安府", "sources": []},
    "reference_images": [],
    "provenance": {
        "researched_at": "2026-10-20T00:00:00+00:00",
        "retriever": "manual",
        "model": "none",
        "confidence": 1.0,
    },
    "status": "draft",
}

CHARACTER_1_WITH_SECRET = dict(CHARACTER)
CHARACTER_1_WITH_SECRET["persona_spec"] = dict(
    CHARACTER["persona_spec"],
    secret="她受人所托，要在今夜把一封密信送出城去",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="M4 WorldSeed 世界链路")
    parser.add_argument("--db", default="narrative_sim.db")
    parser.add_argument("--out", default=str(ROOT / "exports" / "world_events.jsonl"))
    parser.add_argument("--world-id", default="world_yanyu")
    parser.add_argument("--run-id", default="world_run")
    parser.add_argument("--ticks", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--mock", action="store_true", help="用 Mock 后端（离线冒烟）")
    args = parser.parse_args()

    if Path.cwd() != ROOT:
        print(f"错误：cwd 必须是项目根目录 {ROOT}（TinyTroupe 读 ./config.ini），"
              f"当前为 {Path.cwd()}", file=sys.stderr)
        return 2

    if args.mock:
        from orchestrator.persona import MockPersonaBackend
        backend = MockPersonaBackend()
    else:
        from orchestrator.persona_tinytroupe import TinyTroupeBackend
        backend = TinyTroupeBackend()
        backend.reset_cost_stats()
        mode = backend.semantic_mode
        print(f"语义检索：{'真实嵌入服务' if mode == 'real' else f'已降级（{mode}）'}")

    init_db(args.db)
    store = Store(args.db)
    try:
        if store.run_exists(args.run_id):
            print(f"运行 {args.run_id} 已存在，显式重置后重跑")
            store.reset_run(args.run_id)

        store.put_asset(CHARACTER_1_WITH_SECRET)
        store.put_asset(CHARACTER_2)
        store.put_asset(SCENE)
        print("资产入库：char_su_wanqing, char_shen_ke, scene_yanyu_teahouse")

        try:
            events = run_world(
                store, args.run_id, args.world_id,
                ["char_su_wanqing", "char_shen_ke"], "scene_yanyu_teahouse",
                ticks=args.ticks, backend=backend, resume=args.resume,
            )
        except Exception:
            store.finish_run(args.run_id, "failed")
            raise
        print(f"仿真完成: {len(events)} 个事件")

        if not args.mock:
            tokens = backend.collect_total_tokens()
            store.update_run_cost(args.run_id, tokens)
            print(f"token 用量: {tokens}")

        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        export_jsonl(store, args.run_id, args.out)
        validated = store.export_events(args.run_id)
        print(f"导出 {args.out}，复验 {len(validated)} 条全部通过契约校验")
    finally:
        store.close()

    print("验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
