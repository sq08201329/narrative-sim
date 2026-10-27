"""古籍书目无损修复 CLI（017）。

默认只生成候选库和报告；--apply 校验通过后才换库并保留唯一回滚副本。
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.corpus import repair_corpus  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="修复古籍同名覆盖与书目元数据")
    ap.add_argument("root", help="只读藏书根目录")
    ap.add_argument("--db", default="data/corpus.db")
    ap.add_argument("--target", help="候选库路径；默认 <库名>.017.new.db")
    ap.add_argument("--report", default="data/reports/corpus-017-repair.json")
    ap.add_argument("--apply", action="store_true", help="校验成功后替换生产库")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    target = Path(args.target).resolve() if args.target else db.with_name(
        f"{db.stem}.017.new{db.suffix}")
    report = repair_corpus(str(db), str(target), args.root, args.report)
    print(f"候选库: {target}")
    print(f"报告: {Path(args.report).resolve()}")
    print(f"书目 {report['before_books']} → {report['after_books']}；"
          f"恢复 {len(report['recovered'])}；元数据修正 "
          f"{len(report['metadata_changes'])}；异常 {len(report['anomalies'])}")
    if not args.apply:
        print("未替换生产库；确认报告后使用 --apply。")
        return 0

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    backup = db.with_name(f"{db.stem}.pre-017-{stamp}{db.suffix}")
    if backup.exists():
        raise FileExistsError(f"回滚路径已存在: {backup}")
    os.replace(db, backup)
    try:
        os.replace(target, db)
    except Exception:
        os.replace(backup, db)
        raise
    print(f"已应用: {db}")
    print(f"回滚副本: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
