"""M 立项调研纲领 CLI：题材 → 清单（可审阅）→ 批量执行。

用法：
  生成：uv run python scripts/research_brief.py --theme "南宋末年临安城里的情报战" \
          --out briefs/yanyu.json
  执行：uv run python scripts/research_brief.py --execute briefs/yanyu.json [--db PATH]
前置：gptr-mcp 服务在线且 GPTR_MCP_URL 已配置；语义漏斗需嵌入服务（不在线降级）。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from db.init_db import init as init_db  # noqa: E402
from orchestrator.brief import (  # noqa: E402
    BriefError,
    execute_brief,
    generate_brief,
    summarize,
)
from orchestrator.store import Store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="立项调研纲领")
    parser.add_argument("--theme", help="题材文本（生成模式）")
    parser.add_argument("--out", help="清单输出路径（生成模式）")
    parser.add_argument("--execute", metavar="FILE", help="执行指定清单文件")
    parser.add_argument("--db", default="narrative_sim.db", help="SQLite 路径")
    args = parser.parse_args()

    load_dotenv()

    if args.theme:
        if not args.out:
            print("生成模式需要 --out 指定清单输出路径", file=sys.stderr)
            return 2
        try:
            brief = generate_brief(args.theme)
        except BriefError as e:
            print(f"立项失败: {e}", file=sys.stderr)
            return 1
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(brief, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"清单已生成: {out}（{len(brief['items'])} 条"
              f"{'，已按闸门截断' if brief['truncated'] else ''}）")
        for it in brief["items"]:
            print(f"  [{it['category']}] {it['query']}"
                  + (f" → {it['asset_type']}" if it["asset_type"] else ""))
        print("请审阅修改后用 --execute 执行")
        return 0

    if args.execute:
        try:
            brief = json.loads(Path(args.execute).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"清单文件读取失败: {e}", file=sys.stderr)
            return 2
        init_db(args.db)
        store = Store(args.db)
        try:
            ledger = execute_brief(brief, store)
        finally:
            store.close()
        for e in ledger:
            mark = {"stored": "+", "deduplicated": "=", "reused": "↺",
                    "cached": "↺", "merged": "~", "attached": "^",
                    "failed": "✗"}.get(e["status"], "?")
            tail = e["asset_id"] or e["reason"] or ""
            print(f"  {mark} [{e['category']}] {e['query']} → {e['status']} {tail}")
        print(f"总账: {summarize(ledger)}")
        return 0 if not any(e["status"] == "failed" for e in ledger) else 1

    print("需要 --theme（生成）或 --execute（执行）之一", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
