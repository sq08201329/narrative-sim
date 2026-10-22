"""asset_port CLI：主库 → 项目库的资产搬运（export / import / verify）。

用法（项目根执行）：
    python scripts/asset_port.py export --db data/library.db \
        --asset-id char_f2a9f87e4c --out exports/asset_char_f2a9f87e4c.json
    python scripts/asset_port.py import --db data/projects/linan.db \
        --file exports/asset_char_f2a9f87e4c.json
    python scripts/asset_port.py verify --db data/projects/linan.db \
        --file exports/asset_char_f2a9f87e4c.json

退出码：0 成功；1 冲突/校验不齐/手写资产被拒；2 文件损坏或 IO 失败。
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from db.init_db import init as init_db  # noqa: E402
from orchestrator.asset_port import (  # noqa: E402
    AssetPortError,
    BundleCorrupt,
    export_asset,
    import_bundle,
    verify_bundle,
)
from orchestrator.store import Store  # noqa: E402


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _open(db: str) -> Store:
    init_db(db)
    return Store(db)


def _cmd_export(args) -> int:
    store = _open(args.db)
    try:
        summary = export_asset(store, args.asset_id, args.out)
    finally:
        store.close()
    _print(summary)
    if summary["provenance"] == "manual":
        print("警告：该资产 provenance=manual（无调研来源），导入时默认会被拒绝。",
              file=sys.stderr)
    return 0


def _cmd_import(args) -> int:
    store = _open(args.db)
    try:
        plan = import_bundle(
            store, args.file,
            allow_extend=args.allow_extend,
            allow_manual=args.allow_manual,
            backup=not args.no_backup,
            dry_run=args.dry_run,
            db_path=args.db,
        )
    finally:
        store.close()
    _print(plan)
    if plan["provenance"] == "manual":
        print("警告：导入的是手写资产，没有调研来源（provenance=manual）。",
              file=sys.stderr)
    if args.dry_run:
        print("dry-run：未写库。", file=sys.stderr)
    return 0


def _cmd_verify(args) -> int:
    store = _open(args.db)
    try:
        result = verify_bundle(store, args.file)
    finally:
        store.close()
    if args.json:
        _print(result)
    else:
        print(f"资产 {result['asset_id']}（{result['provenance']}）")
        print(f"  资产行：{result['asset'].get('status')} "
              f"dst=r{result['asset'].get('current_revision')} "
              f"期望=r{result['asset'].get('expected_revision')}")
        rev = result["revisions"]
        print(f"  修订：共 {rev['total']}，缺 {rev['missing']}，"
              f"多 {rev['extra']}，不一致 {rev['mismatch']}")
        mat = result["materials"]
        print(f"  原料：共 {mat['total']}，缺 {mat['missing']}，多 {mat['extra']}")
        print(f"结论：{'对齐' if result['ok'] else '不齐'}")
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="资产搬运：export / import / verify（只动 assets、"
                    "asset_revisions、research_materials）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_exp = sub.add_parser("export", help="导出资产 + 全部修订 + 原料")
    p_exp.add_argument("--db", required=True, help="源库路径")
    p_exp.add_argument("--asset-id", required=True)
    p_exp.add_argument("--out", required=True, help="输出 bundle JSON 路径")
    p_exp.set_defaults(func=_cmd_export)

    p_imp = sub.add_parser("import", help="导入 bundle（保号、幂等、冲突不覆盖）")
    p_imp.add_argument("--db", required=True, help="目标库路径")
    p_imp.add_argument("--file", required=True, help="bundle JSON 路径")
    p_imp.add_argument("--allow-extend", action="store_true",
                       help="目标库落后时补齐缺失修订（默认拒绝）")
    p_imp.add_argument("--allow-manual", action="store_true",
                       help="允许导入 provenance=manual 的手写资产（会警告）")
    p_imp.add_argument("--dry-run", action="store_true", help="只打印计划，不写库")
    p_imp.add_argument("--no-backup", action="store_true",
                       help="导入前不备份目标库（默认备份）")
    p_imp.set_defaults(func=_cmd_import)

    p_ver = sub.add_parser("verify", help="核对 bundle 与目标库是否一一对齐")
    p_ver.add_argument("--db", required=True)
    p_ver.add_argument("--file", required=True)
    p_ver.add_argument("--json", action="store_true", help="输出 JSON")
    p_ver.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    load_dotenv()
    try:
        return args.func(args)
    except BundleCorrupt as e:
        print(f"bundle 损坏: {e}", file=sys.stderr)
        return 2
    except AssetPortError as e:
        print(f"搬运失败: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"IO 失败: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
