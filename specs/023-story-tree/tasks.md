---
description: "Task list for 故事时间树"
---

# Tasks: 故事时间树

**Input**: Design documents from `specs/023-story-tree/`

**Tests**: 规格要求系统自查替代人工复核、事件 node_id 锚定与 M1 不回归；先写失败测试再实现。

## Phase 1: Setup

- [X] T001 新增 `schemas/story_tree.schema.json`（tree/nodes/entities/self_check，status 仅 ready），并在 `schemas/event.schema.json` 增加可选 `node_id`（`^n[0-9]{4,}$`，不进 required）— FR-001
- [X] T002 在 `db/init_db.py` 增加幂等 DDL：`story_trees`、`story_nodes`（含 `idx_story_nodes_tree`）— FR-005

## Phase 2: Foundational（阻塞所有用户故事）

- [X] T003 在 `tests/contract/test_story_tree.py` 写失败测试：schema 校验、四项自查（schema/source_span/order/dedup）、source_span 逐字比对失败、无 sqlite 直连 — FR-003/007/008、宪章 I/III
- [X] T004 在 `orchestrator/store.py` 实现树的唯一入口：`put_tree`（先校验 schema，重复 id 需 overwrite）、`get_tree`、`tree_exists`、`list_trees`、`list_tree_nodes`；并把 `export_events` 改为按 `(node_id, tick, seq)` 排序（无 node_id 视为 `""`，保持 M1 等价）— FR-005/013
- [X] T005 在 `orchestrator/story_tree.py` 实现 `parse_story`（注入 `chat_json_fn`，默认 `llm.chat_json`，失败重试一次）、`self_check`（四项，逐字比对 `text[start:end]==quote`）、实体去重与 `map_nodes_to_ticks`（tick 0 归首节点，ticks 不足抛错）— FR-002/003/004/007/008/015

**Checkpoint**: Foundation ready — 用户故事可开始。

## Phase 3: User Story 1 - 导入纯文本生成时间树 (Priority: P1) 🎯 MVP

**Goal**: 纯文本 import 后产出 ready 树 + 自查报告，无需人工确认

**Independent Test**: 注入假 `chat_json` 跑 import，检查 ready 状态、node 顺序、source_span 与四项自查全过；不需要调研/仿真

- [X] T006 [P] [US1] 在 `tests/integration/test_timeline.py` 写失败测试：`import_timeline` 返回 ready / node_count / checks，空文本与非 UTF-8 被拒绝 — US1 AC1/3
- [X] T007 [US1] 在 `orchestrator/workflows.py` 实现 `import_timeline(db_path, tree_id, text, overwrite=False, chat_json_fn=None)`：调 parse_story + self_check，通过后经 store 写库；失败非零、不写库 — FR-004/006/008/009
- [X] T008 [US1] 在 `orchestrator/cli.py` 接入 `timeline` 子命令组与 `timeline import/show`，在 `orchestrator/mcp_server.py` 接入 `import_timeline`/`show_timeline` 薄封装 — FR-014
- [X] T009 [US1] 运行 `uv run pytest -q tests/contract/test_story_tree.py tests/integration/test_timeline.py`，修复直到通过

## Phase 4: User Story 2 - 系统自查保证抽取可靠 (Priority: P1)

**Goal**: 抽查漂移必被自查拦下，自动重试后仍失败则零写入

**Independent Test**: 构造 quote 与原文不符、顺序倒挂、重复规范名的假抽取结果，确认 import 非零退出且库内无树

- [X] T010 [P] [US2] 在 `tests/contract/test_story_tree.py` 增加：span 漂移→重试→失败不写库、order 不一致、entity 重复规范名去重、未 ready 树 drive 零副作用 — US2 AC2/3、SC-002/003/006
- [X] T011 [US2] 在 `orchestrator/story_tree.py` 完善 `self_check` 失败明细（节点 id + 检查名 + 原因）与重试逻辑，确认 `show_timeline` 返回最近一次 self_check — FR-007/008

**Checkpoint**: US1 与 US2 均可独立验证，MVP 完成。

## Phase 5: User Story 3 - 按树驱动调研与建世界 (Priority: P2)

**Goal**: 树中空间/人/物汇成去重调研清单；空间节点成为世界锚点

**Independent Test**: 对 ready 树执行 research 与 world，确认 ledger 只含去重实体、复用四层漏斗、每空间节点有 world 且 config 含 tree_id/node_ids

- [X] T012 [P] [US3] 在 `tests/integration/test_timeline.py` 写失败测试：research 调 `brief.execute_brief`（注入假 fn）且查询词去重、entity_assets 回填；world 按空间节点建世界且节点→资产写入 config — US3 AC1/2/3
- [X] T013 [US3] 在 `orchestrator/story_tree.py` 增加 `build_research_brief`（character→character，scene/prop→world，去重；实体 key 用 `char_/scene/prop_` + sha1(name)[:8] 确定性生成，research 后用 `entity_assets` 解析为真实 asset_id）与 `build_world_specs`（按 location_key 分组，world_id=`{base}__{node_id}`）；在 `orchestrator/workflows.py` 实现 `drive_timeline` 的 research/world 阶段并回填 `entity_assets`/`node_worlds`；drive 入口先校验 ready，否则拒绝 — FR-009/010/011
- [X] T014 [US3] 在 `orchestrator/cli.py` 与 `orchestrator/mcp_server.py` 接入 `timeline drive --stage research|world` 与 `drive_timeline` 薄封装 — FR-014

## Phase 6: User Story 4 - 按树锚定仿真事件并导出 (Priority: P2)

**Goal**: 每个事件带合法 node_id，导出按 node_id → tick → seq，故事事实不被改写

**Independent Test**: 对 ready 树 run（mock 后端）后检查事件 node_id 覆盖率 100%、导出顺序正确、M1 仍通过

- [X] T015 [P] [US4] 在 `tests/integration/test_timeline.py` 写失败测试：run 事件 node_id 覆盖与锚定、导出排序、未解析引用被拒、M1 事件无 node_id 仍通过 — US4 AC1/2/3、SC-004/005
- [X] T016 [US4] 在 `orchestrator/simulation.py` 的 emit 与 `orchestrator/world.py` 的 `run_world` 增加可选 `tick_to_node` 参数（不传则行为不变、事件无 node_id）；在 `orchestrator/workflows.py` 的 `drive_timeline` run 阶段按 world 分组节点并传映射，run_id 多世界派生 `{base}__{node_id}`，入口校验 ready — FR-009/012/015/016
- [X] T017 [US4] 完成 `timeline drive --stage run`、`timeline export` 的 CLI 与 MCP 接入，验证 `narrative export R001` 与 `store.export_events` 的新排序 — FR-013/014

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T018 更新 `README.md`、`mydocs/叙事仿真系统开发手册.md`、`skills/narrative-sim/SKILL.md` 与 `resources/skills/narrative-sim/SKILL.md`：时间树命令、自查门槛、三库边界与仿真复核边界 — FR-017/018
- [X] T019 按 `specs/023-story-tree/quickstart.md` 完成验收，运行 `uv run pytest -q -m "not real"`、`uv run python scripts/run_minimal_chain.py`、契约守卫与 MCP 测试全通过 — FR-016、SC-005

## Dependencies & Execution Order

- Setup → Foundational → US1 → US2 → US3 → US4 → Polish。
- Foundational 未完成前不得开始任何用户故事。
- `chat_json_fn` 与 `research_fn` 等接缝必须可注入，保证离线可测（宪章 IV）。
- 每个故事自带测试，先失败再实现；故事可独立验证后再进入下一个。

## Parallel Opportunities

- T001 与 T002 可并行（schema 与 DDL 不同文件）。
- T006 与 T010 可并行（分别落在集成/契约测试文件）。
- T012 与 T015 可并行（不同测试文件），实现按 T013 → T016 顺序（共用 workflows）。

## Implementation Strategy

先交付 US1+US2 的 MVP（抽取 + 自查 + CLI/MCP 入口），再逐步加 research/world、run/export；全程不碰 M1 入口 `orchestrator/simulation.py` 的默认行为，事件 `node_id` 始终可选。

---

## Phase 8: Convergence (2026-11-18)

- [X] T020 [F1/partial] 在 `tests/integration/test_timeline.py` 注入 self_check.passed=False 的树到 `workflows.drive_timeline`，断言抛 TreeError 且 story_trees/story_nodes/events 无新增 — SC-002
- [X] T021 [F2/partial] 在 `tests/contract/test_story_tree.py` 增加：无 node_id 的既有事件经 `store.export_events` 后仍按 tick → seq 排序，验证 M1 兼容 — FR-013
- [X] T022 [F3/unrequested] 从 `orchestrator/workflows.py` 的 `drive_timeline` 删除未使用的 `chat_json_fn` 形参，并同步 `mcp_server.py` 调用（无该参数） — tasks T013
