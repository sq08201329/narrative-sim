# Tasks: 接入 WorldSeed 世界引擎

**Input**: Design documents from `/specs/006-worldseed-integration/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅（引擎机制行号级证据）、
data-model.md ✅、quickstart.md ✅；无 contracts/（两张契约不动）

**Tests**: 本特性包含测试任务 —— spec 要求离线 Mock 基线（FR-006）与 SC-004 全绿。
测试策略：**真实 WorldSeed 引擎 + MockBackend**（引擎离线可跑，零 LLM）。
测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；核心实现集中在新模块
`orchestrator/world.py`，同文件任务严格串行。

## Phase 1: Setup

- [ ] T001 `uv add --editable /d/kimicode_repos/projects/my_mas/WorldSeed`
  （本地副本路径安装，不装 dm extra）；验证 `from worldseed.world import
  WorldEngine` 可 import 且 `uv run pytest -m "not real" -q` 既有 86 项不回归
  （依赖解析冲突在此暴露）

---

## Phase 2: Foundational（阻塞所有故事）

- [ ] T002 [P] `orchestrator/store.py` 增加 `put_world_state(world_id, tick,
  state_json)` 与 `get_world_state(world_id) -> tuple[int, str] | None`
  （原则 III：仅多两个方法），附离线测试（写读往返 / 无记录返回 None /
  tick 更新覆盖）
- [ ] T003 `orchestrator/world.py` 实现配置组装 `build_scene_config(store,
  character_ids, location_id)`：场景资产 → scene+entities；角色资产
  persona_spec → agents[].character（含 secret 字段）；perception 段
  （hidden_properties/visibility/event_scopes，照 teahouse.yaml 模板）；
  机械效果动作集（say 等，无 DM 段）；资产缺失时明确报错指出缺口（FR-001）

**Checkpoint**: 组装的配置能实例化 WorldEngine 并注册角色（真实引擎冒烟）

---

## Phase 3: User Story 1 - 资产组装世界并跑通引擎 (Priority: P1) 🎯 MVP

**Goal**: 引擎驱动回合推进，事件契约口径与 001 一致，信息不对称可核验

**Independent Test**: 离线真实引擎 + MockBackend 跑 ≥4 回合，契约事件入库；
两角色 perceive 视野存在可核验差异

### Tests for User Story 1（先写，确认失败）

- [ ] T004 [US1] 新建 `tests/contract/test_world_engine.py`（真实引擎 +
  001 的 MockBackend）：配置组装（资产→SceneConfig 各段正确、缺角色报错）；
  世界循环跑 3 tick：事件全部过契约校验、event_id 连续、开场 scene_change
  事件与 001 同形态；信息不对称：两角色 perceive 输出互不含对方 secret、
  视野存在差异

### Implementation for User Story 1

- [ ] T005 [US1] 在 `orchestrator/world.py` 实现世界循环 `run_world(store,
  run_id, world_id, character_ids, location_id, ticks, backend)`：
  引擎生命周期（config→register→每 tick perceive→组装 visible_state→
  backend.act→动作映射 submit→step）→ 契约事件 emit（复用 001 的
  `_SHOT_BY_KIND` 与 emit 口径；visible_state 由 AgentPerception 组装为
  backend 既有 {tick, location, recent_events} 键，backend 接口零改动）；
  动作映射失败被翻译层拦截记录，不产生残缺事件
- [ ] T006 [US1] 实现 `scripts/run_world_chain.py` CLI（--world-id --ticks
  --db [--resume]），结构对照 run_real_chain.py（cwd 守卫/打印/验收口径）

**Checkpoint**: US1 独立成立 —— 离线真实引擎全链路可证

---

## Phase 4: User Story 2 - 状态快照与断点续跑 (Priority: P2)

**Goal**: 每 tick 快照入 worlds.state；中断后续跑编号连续、零重演

**Independent Test**: 离线真实引擎跑 3 tick → 新进程（新引擎实例）
--resume 续跑 2 tick，事件编号连续、零重复、契约全过

### Tests for User Story 2（先写，确认失败）

- [ ] T007 [US2] 在 `tests/contract/test_world_engine.py` 增加：
  每 tick 后 worlds.state 有快照且 tick 递增；save_state→新引擎
  load_state 后续跑，事件编号经 max_event_no 连续、无重复回合；
  损坏快照（非法 JSON）续跑明确报错

### Implementation for User Story 2

- [ ] T008 [US2] 在 `orchestrator/world.py` 实现快照读写：每 tick 结算后
  `engine.save_state()` → `store.put_world_state()`；`run_world(resume=True)`
  时 `get_world_state` → 同配置重建引擎 → `load_state` → 从 tick+1 继续；
  快照反序列化失败明确报错（FR-005 / Edge Case）

**Checkpoint**: US1、US2 均独立成立

---

## Phase 5: User Story 3 - 翻译复用与基线 (Priority: P3)

**Goal**: 翻译口径与 001 一致；M1/M2 基线零改动可运行

**Independent Test**: M1 最小链路真跑输出与 001 验收一致；全量离线套件绿

### Tests for User Story 3

- [ ] T009 [US3] 在 `tests/contract/test_world_engine.py` 增加：
  `_SHOT_BY_KIND` 映射与 001 逐键一致（dialogue/action/inner_voice/
  scene_change/narration）；grep 验证 WorldSeed import 只出现在
  `orchestrator/world.py` 与 `tests/contract/test_world_engine.py`

**Checkpoint**: 三个故事全部独立成立

---

## Phase 6: Polish & 全量验收

- [ ] T010 全量离线回归 `uv run pytest -m "not real"` 全绿（SC-004）
- [ ] T011 真机验收（TinyTroupe 后端 + DeepSeek 密钥）：按 quickstart.md
  场景 2 跑 4 回合（SC-001：≥5 事件、契约全过），场景 3 断点续跑（SC-003），
  场景 5 旧链路对照（M1 真跑一致）
- [ ] T012 本文件全部任务标记 [X]，提交（建议
  `feat(006): world engine integration via WorldSeed adapter`）

---

## Dependencies & Execution Order

- Phase 1（T001）无依赖，最先做（依赖冲突早暴露）
- Phase 2：T002 ∥ T003（不同文件）；Checkpoint 后才能进故事
- US1（Phase 3）依赖 Phase 2；US2（Phase 4）依赖 T005（循环存在才能加快照）
- US3（Phase 5）依赖 T005；Phase 6 依赖全部故事

### Parallel Opportunities

T002 ∥ T003；T004（写测试）与 T003（写组装）可并行收尾；
world.py 上的 T003/T005/T008 严格串行。

## Implementation Strategy

MVP = Phase 1-3（US1）：离线真实引擎全链路成立即交付核心价值；
US2 快照续跑紧随其后（与循环同模块，增量小）；真机验收（T011）放最后，
此时离线证据已充分，真机只验证 LLM 角色在线形态。
