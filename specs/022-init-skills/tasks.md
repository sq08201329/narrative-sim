---
description: "Task list for 初始化与使用技能分发"
---

# Tasks: 初始化与使用技能分发

**Input**: Design documents from `specs/022-init-skills/`

**Tests**: 规格明确要求首次、幂等、技能和冻结验收；先写失败测试再实现。

## Phase 1: Setup

- [X] T001 创建 `resources/skills/narrative-sim/SKILL.md`，覆盖 CLI/MCP、三库边界、离线/真实工作流、服务启停和密钥保护

## Phase 2: Foundational

- [X] T002 在 `tests/contract/test_init_app.py` 覆盖全新初始化、结果字段、缺失模板错误及无服务/数据库副作用
- [X] T003 在 `orchestrator/init_app.py` 实现共享目录创建、模板复制和 created/existing 结果，在 `orchestrator/cli.py` 接入 init 与 start 自动初始化

## Phase 3: User Story 1 - 一条命令完成首次配置 (Priority: P1) — MVP

**Goal**: 全新 HOME 一次获得目录、配置模板和使用技能

**Independent Test**: 开发入口 init 创建全部约定内容，无网络、模型或业务库调用

- [X] T004 [US1] 执行 `tests/contract/test_init_app.py` 与实际 `uv run narrative --home <临时目录> init`，修复直到通过

## Phase 4: User Story 2 - 升级时不覆盖用户内容 (Priority: P2)

**Goal**: 重复 init 和替换程序目录均保留用户文件

**Independent Test**: 修改 config/.env/技能后重复 init，所有已有项为 existing 且字节不变

- [X] T005 [P] [US2] 在 `tests/contract/test_init_app.py` 覆盖已有文件保留、部分缺失补齐与不可写错误
- [X] T006 [US2] 在 `orchestrator/init_app.py` 完成不覆盖与错误处理并执行 P2 验收

## Phase 5: User Story 3 - Agent 获得一致的项目使用技能 (Priority: P3)

**Goal**: 发行包携带模板，冻结 init 生成相同技能

**Independent Test**: 冻结 EXE 在中文空格 HOME 初始化，技能与开发模板一致，ZIP 含模板且无真实数据

- [X] T007 [P] [US3] 在 `tests/integration/test_standalone_app.py` 增加冻结 init、技能一致性和发行资源守卫
- [X] T008 [US3] 在 `packaging/narrative.spec` 与 `scripts/build_standalone.py` 携带 `.env.example` 和技能模板，在 `README.md`/`mydocs/叙事仿真系统开发手册.md` 写明初始化
- [X] T009 [US3] 重建 `dist/NarrativeSim` 与 ZIP，执行冻结 init 和现有冻结回归

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T010 按 `specs/022-init-skills/quickstart.md` 完成全部验收，并运行 `uv run pytest -q -m "not real"`、M1 与 `uv build`

## Dependencies & Execution Order

- Setup → Foundational → US1 → US2 → US3 → 最终验收。
- 模板只有一个来源；显式 init 与 start 必须调用同一初始化函数。
- 冻结代码或资源变化后重建再验收，不修改全局 Agent 配置。

## Parallel Opportunities

- 技能模板与初始化测试可并行准备；契约和冻结测试位于不同文件。

## Parallel Example: User Story 3

```text
契约测试负责模板内容；冻结集成测试负责实际 EXE 与 ZIP 资源。
```

## Implementation Strategy

先完成开发 init MVP，再验证不覆盖，最后打包技能并做冻结验收；不包含模型下载或团队脚手架。
