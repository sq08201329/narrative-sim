# Tasks: 幕间记忆传递

**Input**: Design documents from `/specs/012-interlude-memory/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅、data-model.md ✅、
contracts/interlude.md ✅、quickstart.md ✅

**Tests**: 本特性包含测试任务 —— spec FR-010 与宪章 IV 要求离线零外部调用、
既有 169 项无回归。测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；`orchestrator/world.py` 与
`orchestrator/mcp_server.py` 为共享文件，同文件任务严格串行。

## Phase 1: Setup（表与键位）

- [x] T001 [P] `db/init_db.py`：`interlude_memories` 幂等 DDL（UNIQUE(run_id,
  asset_id, revision) + idx_interlude_run 索引，结构见 data-model.md）
- [x] T002 [P] `.env.example` 增加键位（含注释）：`INTERLUDE_MAX_EVENTS`（50）、
  `INTERLUDE_MAX_CHARS`（4000）

---

## Phase 2: Foundational（存储原语，阻塞所有故事）

- [x] T003 `orchestrator/store.py` 记忆原语：`put_memory(run_id, asset_id,
  summary, event_refs, channel, tokens_in, tokens_out) -> int`（同键自动升
  revision）/ `get_memory(run_id, asset_id) -> dict | None`（当前版）/
  `list_memories(run_id) -> list[dict]`（每角色当前版）
- [x] T004 存储层用例入 `tests/contract/test_interlude.py`：首版 rev1 /
  同键再写升 rev2 旧版留痕 / 读取取当前版 / 空 run 返回 []

**Checkpoint**: 原语就绪，既有 169 项回归绿

---

## Phase 3: User Story 1 - 按角色过滤的记忆注入 (Priority: P1) 🎯 MVP

**Goal**: 三规则过滤 + template 通道 + 双路注入 + 兼容锚点

**Independent Test**: 预置含 inner_voice/visible_to/公开事件的 run，
逐角色断言记忆内容零泄漏；注入后 config 与后端 seeded 可验（quickstart
离线 1/4）

### Tests for User Story 1（先写，确认失败）

- [x] T005 [US1] `tests/contract/test_interlude.py` 主体：过滤三规则逐条
  （inner_voice 仅本人 / visible_to 列内 / 公开全员；SC-001 泄漏率 0）/
  template 确定性（两次逐字节一致）/ 空事件空摘要显式语义 /
  来源 run 不存在 InterludeError / 跨戏交集 skipped 标注（FR-009）
- [x] T006 [US1] 注入用例：run_world(memory_from=...) 后
  build_scene_config 角色卡含 memory 键（空串不加）；Mock 后端
  seeded 记录与记忆一致；不传 memory_from 时输出与现状逐键一致
  （兼容锚点）

### Implementation for User Story 1

- [x] T007 [US1] 实现 `orchestrator/interlude.py`：InterludeError +
  visible_to_character（三规则）+ generate_memories（template 通道 +
  幂等复用 + 交集 skipped）+ get_memories（契约 §1）
- [x] T008 [US1] `orchestrator/persona.py`：PersonaBackend 协议加
  seed_memory；MockPersonaBackend 记录 self.seeded
- [x] T009 [US1] `orchestrator/world.py`：build_scene_config 加
  memories 参数（character 加 memory 键）；run_world 加 memory_from
  （取记忆 → seed 后端 → 传 memories）

**Checkpoint**: US1 离线全绿 + 回归绿

---

## Phase 4: User Story 2 - 记忆可审计、可修订 (Priority: P2)

**Goal**: MCP 读接口 + 幂等复用零重复计费 + 修订沿用版号语义

**Independent Test**: MCP 生成→读取字段齐全；二次生成 reused=True
tokens=0（quickstart 离线 3/5）

### Tests for User Story 2（先写，确认失败）

- [x] T010 [US2] `tests/contract/test_mcp_server.py` 追加：
  generate_interlude_memory / get_interlude_memory 契约（字段完整率
  SC-005）；幂等复用标注；regenerate 升版；RunNotFound / BadChannel；
  EXPECTED_TOOLS 更新

### Implementation for User Story 2

- [x] T011 [US2] `orchestrator/mcp_server.py` 接两个记忆工具（薄封装 +
  错误词汇）

**Checkpoint**: US2 测试全绿

---

## Phase 5: User Story 3 - 双通道与成本控制 (Priority: P3)

**Goal**: llm 通道（chat 接缝 + 预算截断 + token 落库）+ memory_from 进
既有三工具

**Independent Test**: llm 通道 mock chat 接缝可离线测；真机两幕连跑
（quickstart 真机节）

### Tests for User Story 3（先写，确认失败）

- [x] T012 [US3] `tests/contract/test_interlude.py` 追加：llm 通道经 mock
  chat 接缝（注入假 completion）生成摘要、token 落库、输入预算新近优先
  截断生效 / 服务失败不落半成品 / memory_from 经 create_world 冻结进
  config、run_simulation/reshoot 沿用

### Implementation for User Story 3

- [x] T013 [US3] `orchestrator/interlude.py` llm 通道：事件转写（预算截断）
  → chat 接缝（环境桥接 002 模式，MODEL_FAST）→ 摘要落库（token 计量）
- [x] T014 [US3] `orchestrator/mcp_server.py`：create_world /
  run_simulation / reshoot 加 memory_from 参数（create_world 冻结进
  config；run_simulation/reshoot 缺省沿用 config 已冻结值）

**Checkpoint**: US3 测试全绿 + 回归绿

---

## Phase 6: Polish & 真机验收

- [x] T015 全量回归 `uv run pytest -m "not real" -q` 全绿
- [x] T016 真机验收（quickstart 真机节）：world_talk.db talk_r1 生成
  llm 记忆 → 二次生成全复用零计费（SC-003）→ 第二幕带记忆起跑，
  人工核对引用上一幕经历（SC-002）
- [x] T017 标记 tasks.md 全部 [X]；提交

---

## Dependencies & Execution Order

- Phase 1 → 2 → US1 → US2 → US3 → Polish，严格串行（world.py /
  mcp_server.py / interlude.py 为共享文件）
- 可并行：T001 ∥ T002

## Implementation Strategy

MVP = Phase 1-3（US1）：过滤 + template 通道 + 双路注入即可让多幕连续性
离线跑通。US2 补齐审计与 MCP 面，US3 加 llm 质量通道与三工具接线，
Polish 真机两幕连跑验收。

---

## Phase 7: Convergence

- [x] T018 [US2] 补创作队修订记忆入口：`orchestrator/mcp_server.py` 新增
  revise_interlude_memory(run_id, asset_id, summary, reason) 薄封装（经
  store.put_memory 升版，channel="edited"），下一幕注入即取修订版；
  离线测试覆盖修订→读取→注入链路 per US2/AC3 (missing)
