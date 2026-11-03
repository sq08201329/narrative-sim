---
description: "Task list for Windows 独立应用"
---

# Tasks: Windows 独立应用

**Input**: Design documents from `specs/020-standalone-app/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/distribution.md

**Tests**: 包含冻结边界契约和真实 EXE 验收；先写失败测试再改实现。

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 用 `uv add --dev pyinstaller` 更新 `pyproject.toml` 与 `uv.lock`，确认冻结工具版本被锁定
- [X] T002 [P] 新建 `packaging/narrative.spec`，配置 onedir、pathex、GPT/WorldSeed/TinyTroupe 动态模块及 schemas/config/shared/configs/licenses 资源

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T003 在 `tests/contract/test_standalone.py` 覆盖冻结资源根、默认用户 HOME、开发兼容与配置不覆盖规则
- [X] T004 在 `orchestrator/cli.py` 实现冻结 HOME、HOME 下 `.env`/`config.ini` 初始化及内部 `_gptr` 分派，保持公开命令不变
- [X] T005 [P] 在 `orchestrator/store.py` 与 `orchestrator/persona_tinytroupe.py` 适配冻结资源根和用户日志目录，开发行为不变

## Phase 3: User Story 1 - 无开发环境运行现有命令 (Priority: P1) — MVP

**Goal**: 冻结 EXE 不依赖 Python/uv/原仓库即可完成离线全链

**Independent Test**: 在中文空格路径复制发行目录，仅调用 EXE 完成建世界、4 回合 Mock 与导出

### Tests for User Story 1

- [X] T006 [P] [US1] 在 `tests/integration/test_standalone_app.py` 实现冻结 EXE 帮助、离线工作流、任意 cwd 和用户文件位置验收
- [X] T007 [P] [US1] 在 `tests/contract/test_standalone.py` 覆盖冻结运行 TinyTroupe 的工作目录与相对导出路径不变

### Implementation for User Story 1

- [X] T008 [US1] 在 `orchestrator/cli.py` 完成冻结工作目录处理，在 `scripts/build_standalone.py` 实现安全重复构建、README/BUILD-INFO/licenses 和单顶层 ZIP
- [X] T009 [US1] 运行实际构建并在复制后的 `dist/NarrativeSim` 上执行 T006，修复缺失资源直到通过

## Phase 4: User Story 2 - 从发行目录管理完整技术栈 (Priority: P2)

**Goal**: 冻结子进程回调同一 EXE，保持 MCP 和服务生命周期

**Independent Test**: 冻结 EXE 启动 stdio/HTTP MCP 与内部 gptr 服务，客户端可用且停止只影响受管进程

### Tests for User Story 2

- [X] T010 [P] [US2] 在 `tests/contract/test_standalone.py` 覆盖冻结 narrative/gptr 命令不含 python/uv 且所有权标识正确
- [X] T011 [P] [US2] 在 `tests/integration/test_standalone_app.py` 增加冻结 stdio MCP、HTTP MCP 与 gptr 启停验收

### Implementation for User Story 2

- [X] T012 [US2] 在 `orchestrator/services.py` 根据冻结状态回调 `sys.executable`，内部 gptr 使用 `_gptr`，嵌入服务仍使用配置运行时
- [X] T013 [US2] 执行冻结 MCP 与服务验收，修复 stdio 污染、动态导入或进程识别问题

## Phase 5: User Story 3 - 安全升级和迁移用户数据 (Priority: P3)

**Goal**: 程序资源与用户数据完全分离，升级不覆盖用户文件

**Independent Test**: 修改 HOME 配置和数据库后替换程序目录，验证用户文件不变；扫描发行包无真实数据

### Tests for User Story 3

- [X] T014 [P] [US3] 在 `tests/integration/test_standalone_app.py` 覆盖程序目录替换、已有 config.ini 保留及发行包敏感文件扫描

### Implementation for User Story 3

- [X] T015 [US3] 在 `scripts/build_standalone.py` 固定构建排除项与产物清单，在 `README.md` 和 `mydocs/叙事仿真系统开发手册.md` 写明发行、迁移和故障排查

**Checkpoint**: 默认可写文件均在 HOME，程序目录可整体替换，ZIP 内容符合契约

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T016 按 `specs/020-standalone-app/quickstart.md` 完成冻结全链、MCP、服务和数据分离验收，并运行 `uv run pytest -q -m "not real"`、M1 与 `uv build`

## Dependencies & Execution Order

- Setup → Foundational → US1 → US2 → US3 → 最终验收。
- 实际 EXE 失败必须回到对应 spec/路径/资源实现修复，不得以 import 检查代替。
- 构建只触碰 `dist/NarrativeSim` 及同名 ZIP，不清理用户数据或其他目录。

## Parallel Opportunities

- T001/T002、T006/T007、T010/T011 可并行处理不同文件。
- 实际构建与验收必须串行，修复后重新构建再测。

## Parallel Example: User Story 2

```text
tests/contract/test_standalone.py：冻结进程参数。
tests/integration/test_standalone_app.py：真实 EXE 协议与生命周期。
```

## Implementation Strategy

1. 先打通冻结离线 MVP，证明资源和默认 HOME 正确。
2. 再验证多进程与 MCP，最后完成升级/ZIP 卫生。
3. 最终同时跑现有开发回归和冻结应用验收，不包含安装器或自动更新。
