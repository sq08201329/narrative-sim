---
description: "Task list for 古籍书目无损修复"
---

# Tasks: 古籍书目无损修复

**Input**: Design documents from `/specs/017-corpus-metadata-repair/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/corpus-repair.md

**Tests**: spec.md FR-008 明确要求离线回归；每个故事先写失败测试。

## Phase 1: Setup

- [X] T001 建立 017 分支、规格、契约和迁移设计，确认 `.specify/feature.json` 指向本特性

## Phase 2: Foundational

- [X] T002 盘点源目录文件模式、生产库基线和可用磁盘，固定 13,409 TXT / 11 恢复 / 1 空书验收口径于 `specs/017-corpus-metadata-repair/research.md`

## Phase 3: User Story 1 - 恢复每一份 TXT 的独立书目 (Priority: P1)

**Goal**: 同名异路径及同名同内容均不覆盖，历史未冲突 ID 不变。

**Independent Test**: 临时目录创建同名不同内容与同名同内容文件，重复入库并逐路径检查正文。

### Tests for User Story 1

- [X] T003 [US1] 在 `tests/contract/test_corpus.py` 添加同名异路径、同内容、幂等及历史 ID 稳定测试并确认修复前失败

### Implementation for User Story 1

- [X] T004 [US1] 在 `db/corpus.py` 实现路径感知 ID 分配与冲突后缀，保持既有入库签名和检索契约

## Phase 4: User Story 2 - 可信地修正书目元数据 (Priority: P1)

**Goal**: 明确格式正确解析，丛书前缀可证明，异常字段留空可审计。

**Independent Test**: 三段、四段丛书、空作者、卷数、副本及多锚点样例逐字段核对。

### Tests for User Story 2

- [X] T005 [US2] 在 `tests/contract/test_corpus.py` 添加异构文件名、目录丛书匹配和异常留空测试并确认修复前失败

### Implementation for User Story 2

- [X] T006 [US2] 在 `db/corpus.py` 实现保守元数据解析和 `metadata_unresolved` 注记，不使用模型或猜测字段

## Phase 5: 无损迁移与应用

**Goal**: 将两项修复安全应用到既有文库，旧块完全不变。

- [X] T007 在 `tests/contract/test_corpus.py` 添加备份修复、缺失恢复、旧块不变、源库不动及报告测试并确认修复前失败
- [X] T008 在 `db/corpus.py` 实现在线备份、逐路径哈希校验、元数据回填、缺失补入和 JSON 报告；在 `scripts/corpus_repair.py` 实现仅调用入口的盘点/应用 CLI
- [X] T009 运行 `uv run pytest tests/contract/test_corpus.py -q` 与 `uv run pytest -m "not real" -q`，修复所有回归

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T010 按 `specs/017-corpus-metadata-repair/quickstart.md` 生成生产候选库和报告，核对 13,409 书目、11 恢复、旧块不变及检索后显式应用并验证回滚点
- [X] T011 运行 `uv run python scripts/run_minimal_chain.py`，复核契约、文档和任务完成情况

## Dependencies & Execution Order

- T001 → T002 →（T003/T004 与 T005/T006 顺序执行）→ T007/T008 → T009 → T010 → T011。
- US1 与 US2 概念独立，但共同修改 `db/corpus.py` 和同一测试文件，不并行编辑。
- 生产应用 T010 必须等待全部离线测试通过。

## Parallel Example

无代码并行任务；只读盘点与文档校验可并行。

## Implementation Strategy

先修复新入库不再覆盖，再修正解析规则，最后通过同一迁移入口修复历史库。
每一步先以临时文库证明，再处理 22.8GB 生产库；不重建既有全文索引。
