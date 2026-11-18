---
description: "Task list for 创作资产管理技能"
---

# Tasks: 创作资产管理技能

**Input**: Design documents from `specs/024-creative-assets/`

**Tests**: 规格要求 init 分发/不覆盖、移交包 WORKDIR.md 与技能内容守卫；先写失败测试再实现。

## Phase 1: Setup

- [X] T001 新增 `specs/024-creative-assets/` 全套设计产物（spec/plan/research/data-model/contracts/quickstart/checklists）— 已完成，随提交入库

## Phase 2: Foundational

- [X] T002 在 `tests/contract/test_creative_assets.py` 写失败测试：技能存在且六节齐全、frontmatter name/description 正确、三铁律、仓库副本与模板字节一致 — FR-001/002/003/004

## Phase 3: User Story 1 - 可执行的资产管理技能 (Priority: P1) 🎯 MVP

**Goal**: 创作 Agent 加载技能后拿到完整资产管理规范，且不与仿真技能撞触发

**Independent Test**: 检查技能文件与 frontmatter、六节正文、三条铁律与触发边界描述

- [X] T003 [US1] 创建 `resources/skills/creative-assets/SKILL.md`：frontmatter（name=creative-assets、description 写明创作侧资产管理）+ 六节正文（资产来源/编号/归属 first_seen_node/物理布局含命名规则与三铁律/改版与重拍/移交），兼容无 node_id 的退化工序 — FR-002/003/004
- [X] T004 [US1] 复制模板为 `skills/creative-assets/SKILL.md`，确保字节一致；在 `narrative-sim` 技能不动前提下确认两技能 description 触发边界清晰 — FR-001/002
- [X] T005 [US1] 运行 T002 测试，修复直到通过

## Phase 4: User Story 2 - init 分发技能 (Priority: P1)

**Goal**: 开发与冻结 init 都分发技能，已有文件不覆盖

**Independent Test**: 临时 HOME 执行 init 得 created；改后重复 init 得 existing 且字节不变

- [X] T006 [P] [US2] 在 `tests/contract/test_creative_assets.py` 增加 init 分发测试：全新 HOME 创建技能、已有技能不覆盖、缺模板明确失败 — FR-005/006、SC-001/002
- [X] T007 [US2] 在 `orchestrator/init_app.py` 的 TEMPLATES 增加 `skills/creative-assets/SKILL.md` 条目（源=`resources/skills/creative-assets/SKILL.md`），不改既有不覆盖逻辑 — FR-005
- [X] T008 [US2] 运行 init 测试与 `tests/contract/test_init_app.py`，确认开发与冻结资源一致 — FR-006

## Phase 5: User Story 3 - 移交包自带规范 (Priority: P2)

**Goal**: 移交包含 WORKDIR.md，随数据交付且 manifest 自描述

**Independent Test**: export_handoff 产出 WORKDIR.md，manifest items 含 sha256，counts 键不变

- [X] T009 [P] [US3] 在 `tests/contract/test_creative_assets.py` 增加：移交包含 WORKDIR.md、被 manifest items 记录且 sha256 实算一致、counts 键集合不变、既有 HandoffExists 不回归 — FR-007/008、SC-003
- [X] T010 [US3] 新增 `resources/skills/creative-assets/WORKDIR.md`，内容为与技能「物理布局 + 归属」同源的规范文本 — FR-008
- [X] T011 [US3] 在 `orchestrator/handoff.py` 的 `export_handoff` 用 `_write` 写 `WORKDIR.md`（kind=`workdir`），不改 counts；确认 MCP `export_handoff` 参数与返回不变 — FR-007/011
- [X] T012 [US3] 运行 `tests/contract/test_handoff.py` 与 MCP 移交测试，修复直到通过

## Phase 6: User Story 4 - 文档指针 (Priority: P2)

**Goal**: README/手册 30 秒看懂约定并指向技能

**Independent Test**: 两处各有目录树总览、三条铁律与技能指针，既有章节不破坏

- [X] T013 [P] [US4] 在 README.md 增加创作工作目录小节（目录树总览 + 三铁律 + creative-assets 技能指针）— FR-009
- [X] T014 [US4] 在 `mydocs/叙事仿真系统开发手册.md` 增加同样的指针小节，不破坏既有章节 — FR-009
- [X] T015 [US4] 在 `tests/contract/test_creative_assets.py` 增加文档守卫：两处含关键片段与技能指针 — FR-009

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T016 按 `specs/024-creative-assets/quickstart.md` 完成验收，运行 `uv run pytest -q -m "not real"`、`uv run python scripts/run_minimal_chain.py`、契约守卫与 MCP 测试全通过 — FR-011、SC-005

## Dependencies & Execution Order

- Setup → Foundational → US1 → US2 → US3 → US4 → Polish。
- Foundational 未完成前不得开始用户故事。
- 技能模板是 init 与 WORKDIR.md 的共同源；先定稿模板再复制到仓库副本与 WORKDIR.md。
- handoff 改动只写静态文件，不改 counts、不改 MCP 接口。

## Parallel Opportunities

- T006 与 T009 可并行（不同测试文件/段落）。
- T013 与 T014 可并行（不同文档文件）。

## Implementation Strategy

先交付技能本体（US1）作为 MVP，再接 init 分发、移交包规范、文档指针；全程不改 schema/DDL/MCP 接口，M1 与既有测试不回归。

---

## Phase 8: Convergence (2026-11-18)

- [X] T017 [F1/partial] 在 `tests/integration/test_standalone_app.py` 增加 creative-assets 技能的冻结断言：冻结 init 后 `<HOME>/skills/creative-assets/SKILL.md` 与开发模板字节一致，且 `APP/_internal/resources/skills/creative-assets/SKILL.md` 被打包 — SC-002/FR-006
