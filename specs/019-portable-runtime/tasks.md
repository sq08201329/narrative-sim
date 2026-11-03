---
description: "Task list for 可迁移运行时"
---

# Tasks: 可迁移运行时

**Input**: Design documents from `specs/019-portable-runtime/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/paths.md

**Tests**: 包含规格验收所需的路径守卫、服务与隔离副本测试；逻辑改动先写失败测试。

## Phase 1: Setup (Shared Infrastructure)

- [X] T001 将 WorldSeed 上游运行所需的 src/shared/configs/pyproject/README/LICENSE 收拢到 `packages/worldseed/`，包含既有 UTF-8 补丁且不复制虚拟环境或无关工作文件
- [X] T002 [P] 将 gptr-mcp 上游 server/utils/README/LICENSE 收拢到 `packages/gptr-mcp/` 并新增 `packages/gptr-mcp/pyproject.toml`，依赖使用现有 FastMCP Slim 与锁定的 GPT-Researcher 生态

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T003 在根 `pyproject.toml` 注册 WorldSeed/gptr-mcp/GPT-Researcher 三个 workspace 成员和相对 sources，以 uv 更新 `uv.lock` 并验证根环境可导入
- [X] T004 [P] 在 `packages/worldseed/UPSTREAM.md`、`packages/gptr-mcp/UPSTREAM.md` 与 `packages/gpt-researcher/UPSTREAM.md` 记录上游 URL、commit、本地修改、收拢日期及许可证位置

## Phase 3: User Story 1 - 在新位置获得可运行副本 (Priority: P1) — MVP

**Goal**: 仓库不依赖历史外部目录即可完成安装和离线运行

**Independent Test**: 在中文且含空格的隔离副本中安装并运行 M1、CLI 和离线测试

### Tests for User Story 1

- [X] T005 [P] [US1] 在 `tests/contract/test_portable_runtime.py` 增加固定本机路径、workspace 来源、组件资源与许可证守卫
- [X] T006 [P] [US1] 在 `tests/contract/test_cli_services.py` 增加内部 gptr 启动命令与根 Python 环境断言

### Implementation for User Story 1

- [X] T007 [US1] 在 `orchestrator/services.py` 改用 `packages/gptr-mcp/server.py` 和根 Python，消除 `GPTR_ROOT` 与外部 venv 依赖
- [X] T008 [US1] 将 `scripts/start_stack.ps1` 转为保留 Action/DbPath 参数的统一 CLI 薄入口，删除外部绝对路径和第二套进程管理

**Checkpoint**: 根环境安装、MCP 契约与离线链路通过，运行代码不再引用原外部项目路径

## Phase 4: User Story 2 - 统一迁移全部运行数据 (Priority: P2)

**Goal**: HOME 派生三库、日志和运行状态，并支持独立覆盖

**Independent Test**: 在临时 HOME 中验证三库默认值及每个数据库覆盖，旧数据不被修改

### Tests for User Story 2

- [X] T009 [P] [US2] 在 `tests/contract/test_corpus.py` 覆盖 CORPUS_DB 为空/显式值及 `<home>/data/corpus.db` 派生规则
- [X] T010 [P] [US2] 在 `tests/contract/test_cli.py` 覆盖 HOME 下三库路径互不影响及 NARRATIVE_DB 子进程传递

### Implementation for User Story 2

- [X] T011 [US2] 在 `orchestrator/corpus.py` 让未配置或空 CORPUS_DB 使用 `<NARRATIVE_HOME>/data/corpus.db`，保留缺失库的 CorpusUnavailable 行为
- [X] T012 [US2] 在 `orchestrator/cli.py` 统一规范化 NARRATIVE_HOME/NARRATIVE_DB/LIBRARY_DB 并确保 `orchestrator/services.py` 的子进程继承同一组路径

**Checkpoint**: 三库职责不变，HOME 与独立覆盖组合全部符合 contracts/paths.md

## Phase 5: User Story 3 - 在新环境管理外部运行时 (Priority: P3)

**Goal**: 显式配置 LiteRT-LM 与模型文件，缺失提示可执行且不影响离线功能

**Independent Test**: 用伪运行时验证缺失程序、缺失模型、自动导入分支，离线 M1 全程不读取这些资源

### Tests for User Story 3

- [X] T013 [P] [US3] 在 `tests/contract/test_cli_services.py` 覆盖 LITERT_LM、EMBEDDING_MODEL_FILE、EMBEDDING_MODEL 配置和缺失资源错误

### Implementation for User Story 3

- [X] T014 [US3] 在 `orchestrator/services.py` 用 EMBEDDING_MODEL_FILE 取代 EMBEDDING_ROOT，启动前校验文件并保留模型自动导入与健康服务复用
- [X] T015 [US3] 在 `.env.example` 写入可迁移的模型与运行时空缺省配置，移除 GPTR_ROOT/EMBEDDING_ROOT 并说明资源准备方式

**Checkpoint**: 外部资源错误包含配置名，真实服务接口和离线基线不变

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T016 [P] 更新 `README.md`、`data/README.md` 与 `mydocs/叙事仿真系统开发手册.md` 的安装、三库迁移和运行时说明
- [X] T017 [P] 更新 `docs/worldseed-local-patch/README.md`、`mydocs/opensource_repos_dir.md` 与 `KNOWN-LIMITATIONS.md`，移除已解决的外部不可安装限制并保留历史补丁说明
- [X] T018 按 `specs/019-portable-runtime/quickstart.md` 创建隔离副本，执行干净安装、M1、CLI、路径扫描及 `uv run pytest -q -m "not real"`

## Dependencies & Execution Order

- Setup → Foundational → US1 / US2 / US3 → Polish。
- 三个用户故事共享 workspace 基础；按 P1 → P2 → P3 实施，每阶段先跑对应测试。
- T018 必须最后执行，隔离副本不得包含 `.env`、真实数据库、模型或虚拟环境。

## Parallel Opportunities

- T001/T002 收拢不同目录，可并行；T005/T006、T009/T010 涉及不同测试文件，可并行。
- T016/T017 可按不同文档拆分，但须保持路径口径一致。

## Parallel Example: User Story 2

```text
tests/contract/test_corpus.py：验证古籍库派生。
tests/contract/test_cli.py：验证剧目库与调研主库互不干扰。
```

## Implementation Strategy

1. 先收拢包与锁定依赖，交付可迁移的离线 MVP。
2. 再统一三库路径，最后完善外部模型配置。
3. 最终在无历史外部目录、无密钥和无真实数据的隔离副本中验收，不在本特性中打包 PyInstaller。
