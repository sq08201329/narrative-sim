---
description: "Task list for 统一 CLI 应用"
---

# Tasks: 统一 CLI 应用

**Input**: Design documents from `specs/018-cli-application/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli.md

**Tests**: 包含规格验收所需的契约与集成测试；先写测试并确认失败，再实现对应能力。

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 注册 `narrative = "orchestrator.cli:main"` 并用 uv 将 psutil 声明为直接依赖，更新 `pyproject.toml` 与 `uv.lock`
- [X] T002 [P] 在 `.env.example` 增加 `NARRATIVE_HOME`、`GPTR_ROOT`、`EMBEDDING_ROOT`、`LITERT_LM` 配置说明，不写入真实路径或密钥

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 统一路径、命令结果和业务流程，所有用户故事共用

- [X] T003 在 `orchestrator/cli.py` 建立 argparse 入口、全局 `--home`/`--db` 解析、JSON stdout、诊断 stderr 与 0/1/2 退出码骨架
- [X] T004 在 `orchestrator/workflows.py` 提取资产调研、世界创建、运行和导出的共享流程，并让 `orchestrator/mcp_server.py` 改为调用这些函数而保持工具返回结构不变
- [X] T005 [P] 在 `tests/contract/test_mcp_server.py` 增补共享流程后的现有 MCP 行为回归，覆盖世界创建、Mock 运行、导出及不存在 run 的错误

## Phase 3: User Story 1 - 一个命令完成叙事工作流 (Priority: P1) — MVP

**Goal**: 从统一入口完成调研、世界创建、仿真和导出

**Independent Test**: 使用临时数据库和 Mock 后端完成世界创建、4 回合运行及至少 5 条契约事件导出，不启动外部服务

### Tests for User Story 1

- [X] T006 [P] [US1] 在 `tests/contract/test_cli.py` 覆盖帮助、参数优先级、调研/世界/运行/导出 JSON 结果及业务失败的 0/1/2 退出码
- [X] T007 [P] [US1] 在 `tests/integration/test_cli_workflow.py` 覆盖临时 `NARRATIVE_HOME` 下的离线世界创建、Mock 运行、导出及不存在 run 不生成成功产物

### Implementation for User Story 1

- [X] T008 [US1] 在 `orchestrator/cli.py` 实现 `research QUERY --type ...`，调用 `orchestrator/workflows.py` 并返回 asset_id/deduplicated
- [X] T009 [US1] 在 `orchestrator/cli.py` 实现 `world create`、`run`、`export`，接通统一数据库、后端/续跑/裁决/记忆选项及契约 JSON 输出

**Checkpoint**: US1 离线工作流独立通过，真实库与现有 MCP 行为未改变

## Phase 4: User Story 2 - 可靠管理本地服务 (Priority: P2)

**Goal**: 通过统一入口幂等管理 embedding、gptr-mcp 和 narrative MCP

**Independent Test**: 用可控本地进程完成启动、重复启动、状态、重启、停止和重复停止，验证无重复实例且 external 进程不被停止

### Tests for User Story 2

- [X] T010 [P] [US2] 在 `tests/contract/test_cli_services.py` 覆盖 ServiceStatus 的 ready/stopped/unhealthy/external 判定、过期状态与配置路径
- [X] T011 [P] [US2] 在 `tests/integration/test_cli_service_lifecycle.py` 覆盖受管测试服务完整生命周期、端口冲突和非受管进程保护

### Implementation for User Story 2

- [X] T012 [US2] 在 `orchestrator/services.py` 实现 `<home>/run` 原子状态记录、psutil PID/created/command 所有权核验、日志与健康检查
- [X] T013 [US2] 在 `orchestrator/services.py` 实现 embedding → gptr-mcp → narrative MCP 启动及反向停止，继承现有环境口径并支持 external 服务复用/跳过
- [X] T014 [US2] 在 `orchestrator/cli.py` 接入 `start`/`stop`/`restart`/`status`，返回 action/database/services 并确保部分失败不报告整体成功

**Checkpoint**: US2 生命周期独立通过，不包含真实模型调用即可验证进程安全

## Phase 5: User Story 3 - 保持自动化与客户端兼容 (Priority: P3)

**Goal**: 通过统一入口前台启动现有 MCP，保持协议与工具行为

**Independent Test**: 以 `narrative mcp` 启动服务，现有 FastMCP 客户端列工具并完成一次调用

### Tests for User Story 3

- [X] T015 [P] [US3] 在 `tests/integration/test_cli_mcp.py` 覆盖 `narrative mcp` 的 stdio 初始化和统一数据库传递，并验证 stdout 不混入 CLI JSON

### Implementation for User Story 3

- [X] T016 [US3] 在 `orchestrator/cli.py` 实现 `mcp --transport --host --port`，复用 `orchestrator/mcp_server.py` 并保持 stdout 专用于协议

**Checkpoint**: US1、US2、US3 均可独立验收，原 MCP 启动脚本保留兼容

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T017 [P] 更新 `README.md` 的统一命令使用、配置优先级、数据路径和服务管理说明，保留原脚本兼容说明
- [X] T018 [P] 更新 `mydocs/叙事仿真系统开发手册.md` 的入口与运行指引，使其与新 CLI 和宪章一致
- [X] T019 按 `specs/018-cli-application/quickstart.md` 执行离线工作流、服务生命周期和 MCP 验收，并运行 `uv run pytest -q -m "not real"` 与 M1 基线

## Dependencies & Execution Order

- Setup → Foundational → US1 / US2 / US3 → Polish。
- US1、US2、US3 在 Foundational 后可并行；本执行按 P1 → P2 → P3 顺序完成并逐阶段验证。
- 每个用户故事先完成测试并确认失败，再写实现；T004/T005 是防止 CLI 与 MCP 行为分叉的前置条件。

## Parallel Opportunities

- T001 与 T002 涉及不同文件，可并行。
- T006 与 T007、T010 与 T011 分别涉及不同测试文件，可并行。
- T017 与 T018 涉及不同文档，可并行。

## Parallel Example: User Story 1

```text
Contract: tests/contract/test_cli.py
Integration: tests/integration/test_cli.py
两者先独立编写并运行，随后共同约束 orchestrator/cli.py 的实现。
```

## Implementation Strategy

1. 先完成 Setup + Foundational，确认 MCP 回归不变化。
2. 交付 US1 作为 MVP：临时库内完成离线世界、仿真和导出。
3. 增加 US2 的安全服务管理，再增加 US3 的 MCP 入口。
4. 最后更新文档并执行完整离线回归和 quickstart，不在本特性中进行打包。
