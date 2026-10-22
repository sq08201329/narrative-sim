"""M3 调研管线 CLI：查询词 → 契约资产入库。

用法：uv run python scripts/research_asset.py --query "南宋临安城的酒楼" --type scene
前置：gptr-mcp 服务在线且 GPTR_MCP_URL 已配置（见 .env.example）。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from db.init_db import init as init_db  # noqa: E402
from orchestrator.research import ResearchError, research_asset  # noqa: E402
from orchestrator.store import Store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="调研管线：查询词 → 契约资产入库")
    parser.add_argument("--query", required=True, help="调研查询词")
    parser.add_argument("--type", required=True,
                        choices=["character", "prop", "scene", "epoch"],
                        help="资产类型")
    parser.add_argument("--db", default="data/narrative_sim.db", help="SQLite 路径")
    args = parser.parse_args()

    load_dotenv()
    init_db(args.db)
    store = Store(args.db)
    try:
        asset_id = research_asset(args.query, args.type, store)
    except ResearchError as e:
        print(f"调研失败: {e}", file=sys.stderr)
        return 1
    finally:
        store.close()

    print(f"资产入库: {asset_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
