# Tasks: 立项调研纲领与原料入库

**Input**: Design documents from `/specs/009-research-brief/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅、data-model.md ✅、
quickstart.md ✅；无 contracts/（两张契约不动）

**Tests**: 本特性包含测试任务 —— spec 要求离线 Mock 基线与 SC-004 全绿。
测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；核心实现在新模块 `orchestrator/brief.py`
与 `research.py` 的增量，同文件任务严格串行。

## Phase 1: Setup

- [x] T001 [P] `.env.example` 增加键位（含注释）：`BRIEF_MAX_ITEMS`（12）、
  `RESEARCH_SKIP_THRESHOLD`（0.88）、`RESEARCH_ATTACH_THRESHOLD`（0.80）、
  `RESEARCH_MATERIAL_MAX_CHARS`（8000）

---

## Phase 2: Foundational（原料表，阻塞所有故事）

- [x] T002 `db/init_db.py` 增加 `research_materials` 幂等 DDL（表结构见
  data-model.md，含 asset_id/query 两索引）；`orchestrator/store.py` 增加
  `put_material(asset_id, query, retriever, context) -> int` /
  `get_materials(asset_id) -> list[dict]` /
  `get_material_by_query(query) -> dict | None`（取最新一条）
- [x] T003 原料表离线测试（真实 SQLite tmp 库）：写读往返 / 同资产多条追加 /
  按查询取最新 / 无记录返回 None

**Checkpoint**: 原料表读写就绪，既有 111 项回归绿

---

## Phase 3: User Story 1 - 题材一键立项 (Priority: P1) 🎯 MVP

**Goal**: 题材 → 三类清单（可审阅）→ 批量执行（资产类/素材类分流入库）

**Independent Test**: 离线 mock 全流程（生成/执行/分流）；真机一个题材
完成全流程（SC-001）

### Tests for User Story 1（先写，确认失败）

- [x] T004 [US1] 新建 `tests/contract/test_research_brief.py`（mock chat_json
  与 research 接缝）：清单生成（三类齐全/含 query 与 asset_type/闸门截断/
  漂移重试/空题材拒绝）；批量执行（资产类调 research_asset、素材类调
  research_material、单条失败不阻断、总账状态正确）

### Implementation for User Story 1

- [x] T005 [US1] 实现 `orchestrator/brief.py`：`generate_brief(theme)`
  （chat_json 拆解 → 三类校验 → `BRIEF_MAX_ITEMS` 闸门）与
  `execute_brief(brief, store)`（逐条分流执行 + 单条容错 + 总账）
- [x] T006 [US1] `orchestrator/research.py` 增加
  `research_material(query, store, *, link_asset_id=None, call_tool=None)`
  （deep_research 取 context → 截断 `RESEARCH_MATERIAL_MAX_CHARS` →
  put_material；link 未给时经库内匹配挂载，再不沾挂 `lore:<slug>`）；
  `research_asset()` 内嵌原料持久化（成功对新资产、去重命中对已有资产均追加）
- [x] T007 [US1] 实现 `scripts/research_brief.py` CLI：
  `--theme X --out FILE`（只生成）/ `--execute FILE [--db]`（批量执行并
  打印总账）；`tests/contract/test_research_pipeline.py` 补原料持久化断言

**Checkpoint**: US1 独立成立 —— 离线全流程可证

---

## Phase 4: User Story 2 - 调研原料入库 (Priority: P2)

**Goal**: 每次调研原料必入库；去重命中追加不覆盖

**Independent Test**: 离线验证单发 research_asset 成功/去重两路径原料落表；
二次调研记录数增加

### Tests for User Story 2（随 T004/T007 落地，此处确认完整）

- [x] T008 [US2] 在 `tests/contract/test_research_pipeline.py` 与
  `tests/contract/test_research_brief.py` 确认覆盖：成功调研 → 原料记录
  （asset_id/query/retriever/context 齐全且 ≤ 截断上限）；
  去重命中 → 原料追加到已有资产、记录数 +1

**Checkpoint**: US1、US2 均独立成立

---

## Phase 5: User Story 3 - 批量成本容错与防重复漏斗 (Priority: P3)

**Goal**: 四层漏斗（精确缓存/清单内合并/库内复用/attach）+ 闸门与总账

**Independent Test**: 离线覆盖四层全部命中路径与降级路径；
含失败条目批量执行总账如实

### Tests for User Story 3（先写，确认失败）

- [x] T009 [US3] 在 `tests/contract/test_research_brief.py` 增加：
  精确缓存命中（同 query 零调用 status=cached）；
  清单内同义合并（mock 嵌入，status=merged）；
  库内高置信复用（cos≥0.88，资产类零调用 status=reused）；
  中阈值 attach（0.80~0.88 照常调研、原料挂命中资产）；
  素材类高置信命中仍照常调研（仅 link 指向）；
  嵌入不可用降级精确匹配；失败条目不阻断与总账计数

### Implementation for User Story 3

- [x] T010 [US3] 在 `orchestrator/brief.py` 实现四层漏斗（依赖 T005/T006）：
  执行前 `get_material_by_query` → 清单内嵌入合并 → 库内复用匹配
  （`RESEARCH_SKIP_THRESHOLD`/`RESEARCH_ATTACH_THRESHOLD`，
  嵌入经 embedding.embed_texts，None 降级精确匹配）

**Checkpoint**: 三个故事全部独立成立

---

## Phase 6: Polish & 全量验收

- [x] T011 全量离线回归 `uv run pytest -m "not real"` 全绿（SC-004）
- [X] T012 真机全流程（gptr-mcp + 嵌入服务在线）：按 quickstart.md
  场景 2-5——题材生成清单、批量执行（SC-001：≥3 资产 + ≥1 lore 原料）、
  同清单复跑验证 cached/reused 标记（SC-003a）、原料查证（SC-002）
- [X] T013 本文件全部任务标记 [X]，提交（建议
  `feat(009): research brief pipeline + raw material persistence`）

---

## Dependencies & Execution Order

- Phase 1（T001）无依赖；Phase 2（T002→T003）阻塞所有故事
- US1（Phase 3）：T004 ∥ T002/T003；T005/T006 依赖 T002；T007 依赖 T005/T006
- US2（Phase 4）随 T006/T007 落地，T008 确认覆盖
- US3（Phase 5）依赖 T005（执行框架存在才能插漏斗）
- Phase 6 依赖所有故事

### Parallel Opportunities

T001 ∥ T002；T004（写测试）∥ T002/T003；
brief.py 上的 T005/T010 串行，research.py 上的 T006 与 T005 可并行收尾。

## Implementation Strategy

MVP = Phase 1-3（US1）：离线全流程成立即交付核心价值；
US2/US3 为同模块增量依次收口；真机验收（T012）放最后，
只验证"题材→清单→执行→原料/复用标记"在线形态。
