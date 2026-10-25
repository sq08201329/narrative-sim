"""古籍批量入库 CLI（016 T006）。

用法：
    uv run python scripts/corpus_ingest.py <藏书根目录> [--db data/corpus.db]
        [--limit N]（抽样，基准测试用）

目录第一层/第二层 → category_l1/l2。幂等可续跑（断后原命令重跑，
已入库整书 skipped）。终报 {total, ingested, skipped, empty, failed}。
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.corpus import ingest_book, init_corpus, stats  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="古籍批量入库")
    ap.add_argument("root", help="藏书根目录")
    ap.add_argument("--db", default="data/corpus.db")
    ap.add_argument("--limit", type=int, default=0, help="只入前 N 部（采样）")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"目录不存在: {root}", file=sys.stderr)
        return 2
    init_corpus(args.db)

    files = sorted(root.rglob("*.txt"))
    if args.limit:
        files = files[: args.limit]
    total = len(files)
    print(f"发现 {total} 部，目标库 {args.db}")

    counts = {"ingested": 0, "skipped": 0, "empty": 0, "failed": 0}
    failures = []
    t0 = time.monotonic()
    for i, f in enumerate(files, 1):
        rel = f.relative_to(root)
        parts = rel.parts[:-1]
        l1 = parts[0] if len(parts) > 0 else ""
        l2 = parts[1] if len(parts) > 1 else ""
        try:
            r = ingest_book(args.db, str(f), l1, l2)
        except Exception as e:  # 库级异常也按书登记，绝不中断
            r = {"status": "failed", "note": f"{type(e).__name__}: {e}"}
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if r["status"] == "failed":
            failures.append({"path": str(rel), "reason": r.get("note", "")})
        if i % 500 == 0 or i == total:
            dt = time.monotonic() - t0
            print(f"[{i}/{total}] {dt:.0f}s "
                  f"({i / dt:.1f} 部/s) 已入 {counts['ingested']}")
    s = stats(args.db)
    print(f"\n终报: {counts} | 库内: {s['books']} 部 {s['chunks']} 块 "
          f"{s['chars'] / 1e8:.2f} 亿字")
    if failures:
        print(f"失败 {len(failures)} 部（前 5）:")
        for f in failures[:5]:
            print(f"  {f['path']}: {f['reason'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
