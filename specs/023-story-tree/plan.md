# Implementation Plan: 故事时间树

**Branch**: `023-story-tree` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

## Summary

从纯文本故事抽取时间树（空间/人/事/物 + source_span），import 时自动完成四项自查（schema、逐字回指、顺序、去重），通过后置 ready。再按树分阶段复用既有调研漏斗、世界和仿真链路，事件带 `node_id` 锚定节点。新增一个 schema（`story_tree`）、event schema 加可选 `node_id`、项目库两张表、orchestrator 一个核心模块；CLI 与 MCP 只做薄封装。

## Technical Context

**Language/Version**: Python 3.12，uv 管理

**Primary Dependencies**: 标准库、jsonschema、现有 `llm` / `brief` / `store` / `world`

**Storage**: 项目库 SQLite 新增 `story_trees` / `story_nodes` 两表；仍属戏库存储域，入口仍是 `orchestrator/store.py`

**Testing**: pytest 契约/集成测试 + `scripts/run_minimal_chain.py`（M1）离线回归

**Target Platform**: 开发版 macOS/Windows；冻结版沿用同一 CLI（`narrative` / `NarrativeSim.exe`）

**Project Type**: CLI 子命令 + MCP 工具

**Performance Goals**: 单篇故事（默认上限约 20000 字）抽取 + 自查秒级；不引入新服务

**Constraints**: 不新增依赖；测试不联网（注入假 `chat_json`）；M1 行为不变；`node_id` 对既有事件可选

**Scale/Scope**: 1 个新 schema、2 张表、1 个核心模块、CLI `timeline` 4 个子命令、MCP 3 个工具

## Constitution Check

- **I 契约先行**：先加 `schemas/story_tree.schema.json` 并给 `event.schema.json` 加可选 `node_id`，写入前经 jsonschema 校验；不改既有契约语义。通过。
- **II 单一胶水层**：抽取/自查在 `orchestrator/story_tree.py`，编排在 `orchestrator/workflows.py`，MCP 为薄封装。通过。
- **III 存储单一入口**：新表 DDL 在 `db/init_db.py`，全部读写经 `orchestrator/store.py`；仍属戏库同一存储域，不新增入口模块，接缝守卫白名单不变。通过。
- **IV Mock 基线**：`chat_json` 可注入；M1 走 `orchestrator/simulation.py` 且不传 `node_id`，行为不变；树驱动 run 可用 mock 后端离线验收。通过。
- **V UV 依赖**：无新增依赖，沿用 `uv run`。通过。
- **VI 密钥与成本**：沿用 `.env` 与统一 LLM 通道，不引入新供应商；本特性不新增独立 run 成本口径。通过。

## Project Structure

```text
schemas/
├── story_tree.schema.json          # 新增：时间树契约
└── event.schema.json               # 加可选 node_id 字段

db/init_db.py                       # 新增 story_trees / story_nodes DDL

orchestrator/
├── store.py                        # 新增树存取方法 + export_events 按 node_id 排序
├── story_tree.py                   # 抽取、四项自查、tick 映射、实体去重
├── simulation.py                   # emit 增加可选 node_id（M1 不传）
├── world.py                        # run_world 接受可选 tick_to_node
├── workflows.py                    # import/show/drive 编排
├── cli.py                          # timeline 子命令组
└── mcp_server.py                   # 3 个薄封装工具

tests/
├── contract/test_story_tree.py     # schema、自查、单一入口、M1 不回归
└── integration/test_timeline.py    # 端到端（注入假 LLM + mock 后端）

specs/023-story-tree/
├── plan.md / research.md / data-model.md / quickstart.md
├── contracts/story-tree.md
└── tasks.md                        # /skill:speckit-tasks 输出

README.md / mydocs/叙事仿真系统开发手册.md / skills/narrative-sim/SKILL.md
```

**Structure Decision**: 不新建包或数据库文件；全部落在既有 Orchestrator 与项目库，保持单一胶水层与单一写入口。

## Complexity Tracking

无宪章违例，无需记录。
