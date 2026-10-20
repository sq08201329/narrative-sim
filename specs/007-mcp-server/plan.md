# Implementation Plan: MCP Server 协议封装

**Branch**: `007-mcp-server` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-mcp-server/spec.md`

## Summary

新建 `orchestrator/mcp_server.py`：FastMCP 薄封装六个工具
（research_asset / create_world / run_simulation / export_events /
web_search / web_fetch），业务全部复用 orchestrator 既有模块——
create_world/run_simulation 经 worlds.config（001 DDL 闲置列）衔接，
006 的 run_world 签名零改动；错误统一兜为 ToolError（结构化可读、不崩进程）。
入口 `scripts/run_mcp_server.py`（env 配置传输/地址，启动零外部检查）。
离线测试用 fastmcp 进程内客户端 + 真实引擎/Mock 基线，零网络零外部进程。
技术细节见 [research.md](research.md)。

## Technical Context

**Language/Version**: Python 3.12（uv 管理）
**Primary Dependencies**: 新增 `fastmcp-slim[server]`（005 实测形态）；
mcp 2.3.0 / orchestrator 全模块 / gptr-deepseek-retriever 复用
**Storage**: SQLite（store.py 仅加 put/get_world_config 两方法，
worlds.config 列启用）
**Testing**: pytest 离线套件（fastmcp 进程内客户端 + 真实引擎/MockBackend +
004/005 既有 mock 接缝）
**Target Platform**: Windows 本机开发环境
**Performance Goals**: 真后端 run_simulation ≈ 15-30s/tick/角色，
客户端按 120s+60s×ticks 配超时（文档化）
**Constraints**: server 文件零业务逻辑复制（SC-004 grep 门禁）；
启动零外部检查；M1-M6 不回归
**Scale/Scope**: 1 个 server 模块 + 1 个入口脚本 + 1 个测试文件 + store 两方法

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 说明 |
|---|---|---|
| I 契约先行 | ✅ | FR-006：不动两张契约 |
| II 单一胶水层 | ✅ | 协议封装独立成模块且零业务复制（SC-004） |
| III 存储单一入口 | ✅ | worlds.config 经 store.py 两方法读写 |
| IV 适配器隔离 + Mock 基线 | ✅ | 进程内客户端 + 既有 Mock 基线，零外部依赖 |
| V UV 依赖管理 | ✅ | 仅 `uv add "fastmcp-slim[server]"` |
| VI 密钥与成本边界 | ✅ | 传输/地址走环境变量；启动零检查 |
| VII 一特性一分支 | ✅ | 当前分支 `007-mcp-server` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/007-mcp-server/
├── plan.md              # 本文件
├── research.md          # Phase 0：7 项决策（fastmcp 形态/接缝/超时/测试）
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── tasks.md             # Phase 2（/skill:speckit-tasks 产出）
```

### Source Code (repository root)

```text
orchestrator/
├── mcp_server.py         # 新增：build_server() + 六工具薄封装（唯一新协议面）
└── store.py              # 仅加 put_world_config / get_world_config

scripts/
└── run_mcp_server.py     # 新增：启动入口（MCP_TRANSPORT/MCP_HOST/MCP_PORT）

tests/contract/
└── test_mcp_server.py    # 新增：进程内客户端全链 + 错误语义 + SC-004 grep
```

**Structure Decision**: 协议层独立成模块（手册命名沿用）；006/004/005 的
orchestrator 模块全部零改动（store 仅加两方法）。

## Complexity Tracking

无（Constitution Check 全过）。
