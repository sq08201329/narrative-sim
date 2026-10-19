"""M2 真后端链路：与 run_minimal_chain.py 同构，仅后端注入为 TinyTroupeBackend。

用法（cwd 必须是项目根目录，TinyTroupe 读 ./config.ini）：
    uv run python scripts/run_real_chain.py [--db PATH] [--out PATH] [--run-id ID]

前置：.env 含有效 OPENAI_API_KEY / OPENAI_BASE_URL（或 DEEPSEEK_*，由后端桥接）。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from db.init_db import init as init_db  # noqa: E402
from orchestrator.persona_tinytroupe import TinyTroupeBackend  # noqa: E402
from orchestrator.simulation import export_jsonl, run_simulation  # noqa: E402
from orchestrator.store import Store  # noqa: E402
from run_minimal_chain import CHARACTER, SCENE  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="M2 真后端仿真链路")
    parser.add_argument("--db", default="narrative_sim.db")
    parser.add_argument("--out", default=str(ROOT / "exports" / "real_events.jsonl"))
    parser.add_argument("--run-id", default="real_run")
    args = parser.parse_args()

    if Path.cwd() != ROOT:
        print(f"错误：cwd 必须是项目根目录 {ROOT}（TinyTroupe 读 ./config.ini），"
              f"当前为 {Path.cwd()}", file=sys.stderr)
        return 2

    backend = TinyTroupeBackend()
    backend.reset_cost_stats()

    init_db(args.db)
    store = Store(args.db)
    try:
        if store.run_exists(args.run_id):
            print(f"运行 {args.run_id} 已存在，显式重置后重跑")
            store.reset_run(args.run_id)

        store.put_asset(CHARACTER)
        store.put_asset(SCENE)
        print("资产入库：char_su_wanqing, scene_yanyu_teahouse")

        try:
            events = run_simulation(
                store, args.run_id, "world_m1",
                ["char_su_wanqing"], "scene_yanyu_teahouse",
                ticks=4, backend=backend,
            )
        except Exception:
            store.finish_run(args.run_id, "failed")
            raise
        print(f"仿真完成: {len(events)} 个事件")

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
