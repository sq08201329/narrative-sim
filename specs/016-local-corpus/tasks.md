# Tasks: 古籍文库（本地语料检索层）

**Input**: Design documents from `/specs/016-local-corpus/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅、data-model.md ✅、
contracts/corpus.md ✅、quickstart.md ✅

**Tests**: 本特性包含测试任务 —— spec FR-010 与宪章 IV 要求离线零外部调用、
既有 242 项无回归。测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；`db/corpus.py` 为存储域核心文件严格串行。

## Phase 1: Setup（宪章修正 + schema v2）

- [x] T001 [P] `.specify/memory/constitution.md` 原则 III 措辞修正为
  "每个存储域单一入口：戏库 store.py；古籍文库 db/corpus.py"，版本
  1.0.0 → 1.0.1（PATCH），Sync Impact Report 入文件头注释（R6）
- [x] T002 `db/corpus.py` schema v2：books 补 category_l1/l2、
  content_hash、chunk_count、char_count、note、ingested_at；chunks 补
  chapter/section/heading_path；init_corpus 幂等（旧 spike 库可弃，
  测试库不入 git）

---

## Phase 2: User Story 1 - 全库入库与结构感知检索 (Priority: P1) 🎯 MVP

**Goal**: 批量入库 + 结构分块 + 检索三件套（关键词/过滤/浏览）

**Independent Test**: 迷你语料 fixture 两本伪古籍（含卷/篇目/无标点退化）
全链断言（quickstart 离线 1-3）

### Tests for User Story 1（先写，确认失败）

- [x] T003 [US1] `tests/contract/test_corpus.py`：结构分块（标题行识别 →
  chapter/section/heading_path 正确；无标点退化定长 + note 注记）/
  编码探测（GB18030 fixture 正确解码）/ 文件名解析（合规与不合规）/
  幂等（重入 skipped 零重复块；改内容重建）/ 单书失败不阻断

### Implementation for User Story 1

- [x] T004 [US1] `db/corpus.py` 实现 ingest_book v2（编码探测 →
  元数据解析 → 结构分块 → 哈希幂等 → 事务内 FTS 同步；返回
  status 字典，契约 §1）
- [x] T005 [US1] `db/corpus.py` 实现 search/browse/stats（FTS5 trigram +
  2 字 LIKE 回退 + 过滤叠加 + 书目浏览 + 规模统计）
- [x] T006 [US1] `scripts/corpus_ingest.py` 批量 CLI：walk 藏书目录
  （目录一二层 → category_l1/l2）、逐部 ingest、进度输出、终报
  {total, ingested, skipped, empty, failed}
- [ ] T007 [US1] 真机全量入库（后台）：藏书根目录 → data/corpus.db，
  验收 SC-001（完成率 ≥99%）+ SC-002（皇城司/茶肆/夜市命中篇目级出处）

**Checkpoint**: US1 离线全绿 + 全量库可用

---

## Phase 3: User Story 2 - 调研管线接古籍腿 (Priority: P2)

**Goal**: research_material 先古籍后 web，典籍原文+转写入原料表

**Independent Test**: mock chat 转写 + 迷你语料，原料条目 retriever 含
书名篇目；零命中/库缺失降级标注（quickstart 离线 5）

### Tests for User Story 2（先写，确认失败）

- [x] T008 [US2] `tests/contract/test_corpus.py` 追加：古籍腿全链
  （mock chat → put_material 字段与 retriever 格式）/ 零命中返回 [] /
  CorpusUnavailable / research_material(use_corpus) 双腿并存与降级

### Implementation for User Story 2

- [x] T009 [US2] 实现 `orchestrator/corpus.py`：CorpusUnavailable +
  corpus_materials（检索 → llm 转写接缝 → put_material）+
  corpus_knowledge
- [x] T010 [US2] `orchestrator/research.py`：research_material 加
  use_corpus=True 参数（先古籍后 web，降级标注）
- [x] T011 [US2] 真机古籍腿调研（quickstart 真机 3）：library.db 一个
  南宋题材 query，原料条目人工核对与原文一致（SC-003）

**Checkpoint**: US2 测试全绿 + 真机原料验证

---

## Phase 4: User Story 3 - 检索面开放 (Priority: P2)

**Goal**: MCP 双工具 + DM 古籍史料源

**Independent Test**: MCP corpus_search/corpus_browse 契约；DMOptions
use_corpus 后 dm_knowledge 含典籍段落

### Tests for User Story 3（先写，确认失败）

- [x] T012 [US3] `tests/contract/test_mcp_server.py` 追加：双工具契约 +
  CorpusUnavailable + EXPECTED_TOOLS 更新；`test_corpus.py` 追加
  DM use_corpus 注入用例

### Implementation for User Story 3

- [x] T013 [US3] `orchestrator/mcp_server.py` 接 corpus_search /
  corpus_browse（薄封装 db/corpus.py）
- [x] T014 [US3] `orchestrator/world.py`：DMOptions 加 use_corpus
  （默认 False 兼容锚点）；build_dm_knowledge 扩展：True 时先
  corpus_knowledge（场景名+角色名各 top-2）后原料（R4）

**Checkpoint**: US3 测试全绿 + 回归绿

---

## Phase 5: User Story 4 - 命中集嵌入精排 (Priority: P3)

**Goal**: search rerank=True 命中集重排 + 降级标记

**Independent Test**: mock embed 下重排与降级断言（quickstart 离线 4）

### Tests for User Story 4（先写，确认失败）

- [x] T015 [US4] `tests/contract/test_corpus.py` 追加：mock embed 重排
  （相关性序变化）/ 嵌入异常降级 rerank_degraded=True / 命中 ≤1 或
  >200 不调用 embed（成本闸）

### Implementation for User Story 4

- [x] T016 [US4] `db/corpus.py` search 加 rerank/embed 参数：命中集
  ≤300 字细分 → embed 接缝 → 余弦重排；异常降级标注

**Checkpoint**: US4 测试全绿

---

## Phase 6: Polish & 收尾

- [x] T017 全量回归 `uv run pytest -m "not real" -q` 全绿
- [x] T018 MCP 双工具真机冒烟（start_stack 在线，corpus_search("夜禁")
  亚秒，SC-004）；data/README.md 补 corpus.db 一节（现行三库）
- [x] T019 标记 tasks.md 全部 [X]；提交

---

## Dependencies & Execution Order

- Phase 1 → US1 → US2 → US3 → US4 → Polish，严格串行（db/corpus.py 共享）
- 可并行：T001 ∥ T002

## Implementation Strategy

MVP = Phase 1-2（US1）：全库入库 + 关键词检索即独立可用（spike 已证明
价值）。US2/US3 接入生产线与开放面，US4 质量增强，Polish 收尾。
