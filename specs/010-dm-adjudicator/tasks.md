# Tasks: DM 裁判启用（真实裁决提供者）

**Input**: Design documents from `/specs/010-dm-adjudicator/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅、data-model.md ✅、
contracts/dm-provider.md ✅、quickstart.md ✅

**Tests**: 本特性包含测试任务 —— spec US3 与宪章 IV 要求离线 Mock 基线全绿、
零外部调用。测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；`orchestrator/world.py` 被多个故事触碰，
同文件任务严格串行；`orchestrator/dm.py`（新文件）与测试文件可并行。

## Phase 1: Setup

- [x] T001 [P] `.env.example` 增加键位（含注释）：`DM_KNOWLEDGE_CHARS`（2000）、
  `DM_MAX_CALLS`（50）、`DM_TIMEOUT_S`（30）

---

## Phase 2: Foundational（裁决审计表，阻塞 US1）

- [x] T002 `db/init_db.py` 增加 `dm_calls` 幂等 DDL（字段与
  `idx_dm_calls_run` 索引见 data-model.md，与引擎 dm_call record 载荷对齐）；
  `orchestrator/store.py` 增加 `put_dm_call(run_id, tick, action, agent_id,
  params, hint, narrative, effects, tokens_in, tokens_out, elapsed_s, failed)
  -> int` / `list_dm_calls(run_id) -> list[dict]`（按 id 升序）
- [x] T003 审计表离线测试（真实 SQLite tmp 库，追加进
  `tests/contract/test_dm_adjudicator.py`）：写读往返 / 同 run 多条按序 /
  失败行 failed=1 且 effects="[]" / 空 run 返回 []

**Checkpoint**: dm_calls 读写就绪，既有 130 项回归绿

---

## Phase 3: User Story 1 - 角色动作获得真实裁决 (Priority: P1) 🎯 MVP

**Goal**: act 动作经真实裁决者判定，叙事进事件流、效果落世界状态、越界重试、
审计落库

**Independent Test**: MockDMProvider 引擎层全流程离线可测（quickstart 离线
验证 1-4）；真机 --dm run 产出非平凡状态变更（SC-002）

### Tests for User Story 1（先写，确认失败）

- [x] T004 [US1] `tests/contract/test_dm_adjudicator.py` 主体：
  兼容锚点（dm=None 时 build_scene_config 输出与 006 版逐键一致，无 dm/
  dm_knowledge/max_dm_calls 键）；DMOptions 注入（act.dm 存在且含 hint/
  allowed_ops/max_effects，say/whisper 无 dm；scene.max_dm_calls 生效）；
  build_dm_provider 无密钥抛 DMConfigError 且消息含缺失键名、桥接不覆盖
  已有 OPENAI_*

### Implementation for User Story 1

- [x] T005 [P] [US1] 实现 `orchestrator/dm.py`：`DMConfigError` +
  `build_dm_provider(options)`（DEEPSEEK_*→OPENAI_* 桥接仅补缺、
  模型串 `openai/{options.model}`、构造 LiteLLMDMProvider(timeout, max_retries)，
  契约见 contracts/dm-provider.md §1）
- [x] T006 [US1] `orchestrator/world.py`：`DMOptions` dataclass（字段与默认
  见 data-model.md）；`build_scene_config(..., dm=None)` 增加 dm 分支
  （act 挂 DMConfig、scene.max_dm_calls；dm_knowledge 先留空串占位，
  US2 填充）；`run_world(..., dm=None)` dm 非 None 时
  `build_dm_provider` 并传入 WorldEngine
- [x] T007 [US1] `orchestrator/world.py`：`_CaptureRecorder` 增加
  `record(kind, tick, **data)` 捕获 kind=="dm_call" 入缓冲；`run_world`
  结束后逐条 `store.put_dm_call`（审计字段映射见 contracts §4）
- [x] T008 [US1] `scripts/run_world_chain.py` 增加 `--dm` /
  `--dm-knowledge-chars N`（2000）/ `--dm-max-calls N`（50）；
  不带 --dm 行为不变；--dm 缺密钥时退出码非零且消息指明缺哪个键

**Checkpoint**: US1 离线测试全绿 + 既有回归绿

---

## Phase 4: User Story 2 - 史料约束裁决 (Priority: P2)

**Goal**: 入库调研原料注入 scene.dm_knowledge，裁决受史料约束

**Independent Test**: 预置原料的库生成 scene config，dm_knowledge 含原料要点、
不超预算；无原料为空串（quickstart 离线验证 2 后半）

### Tests for User Story 2（先写，确认失败）

- [x] T009 [US2] `tests/contract/test_dm_adjudicator.py` 追加：
  build_dm_knowledge 多资产汇总（【query】前缀格式）/ 预算截断（整条丢弃
  尾部）/ 无原料返回 "" / 缺料资产跳过不抛；scene.dm_knowledge 端到端注入

### Implementation for User Story 2

- [x] T010 [US2] `orchestrator/dm.py` 实现
  `build_dm_knowledge(store, asset_ids, budget=2000)`（契约 §2）；
  `orchestrator/world.py` build_scene_config dm 分支接入（asset_ids =
  character_ids + location_id，预算取 options.knowledge_chars）

**Checkpoint**: US2 测试全绿

---

## Phase 5: User Story 3 - 离线开发与故障降级 (Priority: P3)

**Goal**: Mock 基线不受影响；裁决服务失败走引擎内建降级，run 不中断

**Independent Test**: FailingMockDMProvider 连续失败 run 完成且
dm_calls 全 failed=1；全量离线套件零外部调用（SC-004/005）

### Tests for User Story 3（先写，确认失败）

- [x] T011 [US3] `tests/contract/test_dm_adjudicator.py` 追加：
  FailingMockDMProvider（fail_count 大于引擎重试）驱动 run_world
  正常结束、dm_calls 含 failed=1 行、事件流含兜底叙事；
  全离线套件未发现外部调用（socket 护网或 monkeypatch 断言）

### Implementation for User Story 3

- [x] T012 [US3] 若 T011 暴露缺口则修补（预期零代码：降级路径引擎内建，
  research.md R7；本任务兜底）

**Checkpoint**: US3 测试全绿，130+n 回归绿

---

## Phase 6: Polish & 真机验收

- [x] T013 全量回归 `uv run pytest -m "not real" -q` 全绿；`uv lock --check`
  无依赖变更
- [ ] T014 真机验收（quickstart）：`world_talk.db` 沈刻对手戏资产
  `--dm --dm-max-calls 20` 跑 6 tick——dm_calls 覆盖率 100%、至少一行
  effects 非空且快照可见变更、叙事不替他人演戏；故障注入（错误
  DEEPSEEK_BASE_URL）run 完成率 100%（SC-001/002/004）
- [ ] T015 真机验收（可选，yanyu.db）：史料注入后裁决叙事与原料一致，
  人工核对（SC-002 后半）
- [ ] T016 标记 tasks.md 全部 [X]；提交

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1 → US2 → US3 → Polish，严格串行（同文件 world.py）
- 可并行：T001 ∥ T002；T005（dm.py 新文件）∥ T004 测试编写

## Implementation Strategy

MVP = Phase 1-3（US1）：act 动作真实裁决 + 审计落库即可独立交付价值。
US2 叠加史料约束，US3 为合规验证层，Polish 收尾真机验收。
