"""narrative-sim 统一命令行入口。"""
import argparse
import json
import os
import sys
from pathlib import Path

import dotenv

ROOT = Path(__file__).resolve().parent.parent


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("必须是正整数")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="narrative", description="叙事仿真统一命令行：调研、世界、仿真、导出与服务")
    parser.add_argument("--home", help="应用数据根目录（也可设 NARRATIVE_HOME）")
    parser.add_argument("--db", help="剧目 SQLite 路径（也可设 NARRATIVE_DB）")
    parser.add_argument("--library-db", help="调研主库路径（也可设 LIBRARY_DB）")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("start", "启动完整技术栈"),
                            ("stop", "停止受管服务"),
                            ("restart", "重启完整技术栈"),
                            ("status", "查看技术栈状态")):
        commands.add_parser(name, help=help_text)

    research = commands.add_parser("research", help="调研资产并入库")
    research.add_argument("query")
    research.add_argument("--type", required=True,
                          choices=["character", "prop", "scene", "epoch"])

    world = commands.add_parser("world", help="世界管理")
    world_commands = world.add_subparsers(dest="world_command", required=True)
    create = world_commands.add_parser("create", help="创建世界并冻结资产版号")
    create.add_argument("world_id")
    create.add_argument("--characters", required=True, help="逗号分隔的角色资产 ID")
    create.add_argument("--location", required=True, help="场景资产 ID")
    create.add_argument("--reset", action="store_true")
    create.add_argument("--memory-from")

    run = commands.add_parser("run", help="运行世界仿真")
    run.add_argument("world_id")
    run.add_argument("--run-id", required=True)
    run.add_argument("--ticks", type=_positive_int, default=4)
    run.add_argument("--backend", choices=["tinytroupe", "mock"], default="tinytroupe")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--dm", action="store_true")
    run.add_argument("--dm-max-calls", type=_positive_int, default=50)
    run.add_argument("--dm-knowledge-chars", type=_positive_int, default=2000)
    run.add_argument("--memory-from")

    export = commands.add_parser("export", help="导出事件 JSONL")
    export.add_argument("run_id")
    export.add_argument("--out", required=True)

    mcp = commands.add_parser("mcp", help="前台运行 MCP 服务")
    mcp.add_argument("--transport", choices=["streamable-http", "stdio"],
                     default="streamable-http")
    mcp.add_argument("--host", default=os.environ.get("MCP_HOST", "localhost"))
    mcp.add_argument("--port", type=_positive_int,
                     default=int(os.environ.get("MCP_PORT", "8300")))
    return parser


def _paths(args) -> tuple[Path, Path, Path]:
    home = Path(args.home or os.environ.get("NARRATIVE_HOME") or ROOT).resolve()
    db = Path(args.db or os.environ.get("NARRATIVE_DB") or
              home / "data" / "projects" / "linan.db").resolve()
    library_db = Path(args.library_db or os.environ.get("LIBRARY_DB") or
                      home / "data" / "library.db").resolve()
    return home, db, library_db


def _run_mcp(args, db: Path) -> int:
    os.environ["NARRATIVE_DB"] = str(db)
    from .mcp_server import build_server
    server = build_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=args.transport, host=args.host, port=args.port)
    return 0


def _dispatch(args, home: Path, db: Path, library_db: Path):
    from . import workflows

    if args.command == "research":
        return workflows.research(str(library_db), args.query, args.type)
    if args.command == "world":
        characters = [item.strip() for item in args.characters.split(",") if item.strip()]
        if not characters:
            raise ValueError("--characters 至少需要一个角色资产 ID")
        return workflows.create_world(
            str(db), args.world_id, characters, args.location,
            reset=args.reset, memory_from=args.memory_from)
    if args.command == "run":
        return workflows.run_simulation(
            str(db), args.world_id, args.run_id, args.ticks, backend=args.backend,
            resume=args.resume, dm=args.dm, dm_max_calls=args.dm_max_calls,
            dm_knowledge_chars=args.dm_knowledge_chars,
            memory_from=args.memory_from)
    if args.command == "export":
        return workflows.export_events(str(db), args.run_id, args.out)
    if args.command in {"start", "stop", "restart", "status"}:
        from . import services
        return services.service_action(args.command, home, db)
    raise ValueError(f"未知命令: {args.command}")


def main(argv: list[str] | None = None) -> int:
    dotenv.load_dotenv(ROOT / ".env")
    args = build_parser().parse_args(argv)
    home, db, library_db = _paths(args)
    try:
        if args.command == "mcp":
            return _run_mcp(args, db)
        result = _dispatch(args, home, db, library_db)
        print(json.dumps(result, ensure_ascii=False))
        if args.command == "status" and not result["ready"]:
            return 1
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
