# Tasks: uv 项目脚手架与最小仿真链路（M1）基线

**Input**: Design documents from `specs/001-uv-m1-baseline/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: 本特性包含测试任务 —— spec 的 SC-002/SC-003 与 plan 的 `tests/` 结构要求自动化验证。

**Organization**: 任务按用户故事分组，每个故事可独立实现、独立验收。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1/US2/US3，对应 spec.md）
- 所有任务含确切文件路径

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: uv 工程骨架与环境模板

- [ ] T001 在仓库根执行 `uv init`（application 形态），创建 `pyproject.toml`：项目名 `narrative-sim`，`requires-python = ">=3.12"`；不配置打包发布
- [ ] T002 执行 `uv add jsonschema openai python-dotenv` 与 `uv add --dev pytest`，生成并核对 `uv.lock`（依赖 T001）
- [ ] T003 [P] 创建 `.env.example`：`DEEPSEEK_API_KEY=` / `DEEPSEEK_BASE_URL=https://api.deepseek.com` / `MODEL_FAST=deepseek-flash` / `MODEL_SMART=deepseek-flash`；确认 `.env` 已被 `.gitignore` 覆盖

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 契约、存储与胶水层 —— 所有用户故事的前置

**⚠️ CRITICAL**: 本阶段未完成前，任何用户故事不得开工

- [ ] T004 [P] 编写 `schemas/asset.schema.json`：`asset_id` 必填且 pattern `^(char|prop|scene|epoch)_[a-z0-9_]+$`；`type` 必填枚举 `character/prop/scene/epoch`；`name` 必填非空；`provenance` 必填（含 `researched_at/retriever/model/confidence`）；当 `type=character` 时 `appearance`（含 `visual_prompt`）与 `persona_spec`（含 `age/occupation/personality/beliefs/speech_style`）必填；`status` 枚举 `draft/verified/deprecated`
- [ ] T005 [P] 编写 `schemas/event.schema.json`：`event_id` 必填且 pattern `^e[0-9]{4,}$`；`run_id`、`tick`（integer ≥0）、`seq`（integer ≥0）、`type`（枚举 `dialogue/action/scene_change/narration/inner_voice`）、`characters`（array，仅 asset_id 引用，不得含外貌文本）、`location`（scene 类资产 ID）、`content`、`cause_refs`（event_id 数组）、`shot_hint`（`camera/duration_s/style`）、`created_at` 必填
- [ ] T006 实现 `db/init_db.py`：幂等建 `assets`（`asset_id` 主键 + `type/name/status/payload`）、`worlds`、`runs`（含 `token_cost REAL DEFAULT 0`）、`events` 四表；建 `idx_assets_type` 与 `idx_events_run(run_id, tick, seq)` 索引；重复执行不报错、不破坏既有数据
- [ ] T007 实现 `orchestrator/store.py`：`Store` 类提供 `put_asset / get_asset / create_run / put_event / export_events`；`put_asset` 与 `put_event` 入库前经 `schemas/` 对应 Schema 校验，失败抛出格式为 `<schema名> 校验失败: <JSON路径>: <原因>` 的错误；`create_run` 对已存在的 `run_id` 抛明确错误（research.md D5）；`export_events` 按 `tick, seq` 排序返回（依赖 T004、T005）
- [ ] T008 [P] 实现 `orchestrator/llm.py`：懒加载 OpenAI 兼容 client；import 阶段不读密钥；`chat(messages, tier)` / `chat_json(messages, tier)` 首次调用时若无 `DEEPSEEK_API_KEY` 抛出指明缺失环境变量的明确错误；模型名从 `MODEL_FAST` / `MODEL_SMART` 读取（宪章原则 VI 接缝，M1 链路不调用）
- [ ] T009 实现 `orchestrator/persona.py`：`PersonaBackend` Protocol（`act(persona_spec: dict, visible_state: dict) -> dict`，返回 `{"kind": "dialogue|action|inner_voice", "content": str, "emotion": str}`）+ `MockPersonaBackend`：纯 tick 驱动的确定性剧本，无随机、无外部调用
- [ ] T010 实现 `orchestrator/simulation.py`：`run_simulation(store, run_id, world_id, character_ids, location_id, ticks, backend)` —— tick=0 发 `scene_change` 帧；1..N 回合按序遍历角色调 `backend.act`；`cause_refs` 链接该角色上一事件 ID；`shot_hint` 按事件类型映射 camera/duration_s；`export_jsonl(store, run_id, out_path)` 按 tick/seq 逐行写出（`ensure_ascii=False`）（依赖 T007、T009）

**Checkpoint**: 契约 + 存储 + 胶水层就绪，用户故事可开工

---

## Phase 3: User Story 1 - 从零到「验收通过」 (Priority: P1) 🎯 MVP

**Goal**: 干净检出下 3 条命令跑通最小链路，输出「验收通过」并产出契约合法的事件流

**Independent Test**: 删除 `.venv` 与数据库文件后执行 quickstart 三步，脚本输出「验收通过」

### Tests for User Story 1

> **NOTE: 先写测试并确认 FAIL，再实现**

- [ ] T011 [US1] 编写 `tests/integration/test_minimal_chain.py`：调用最小链路入口，断言 —— 退出码 0；导出 JSONL 存在且 ≥5 事件；逐条通过 `schemas/event.schema.json` 校验；连续两次运行事件序列一致（除 `created_at` 外逐字节相同）。先运行确认 FAIL（脚本尚不存在）

### Implementation for User Story 1

- [ ] T012 [US1] 实现 `scripts/run_minimal_chain.py`：`db/init_db.py` 初始化 → `store.put_asset` 入库 1 名示例角色（`character`，含完整 `appearance.visual_prompt` 与 `persona_spec`）+ 1 个示例场景（`scene`）→ `create_run` → `run_simulation(ticks=4, backend=MockPersonaBackend())` → `export_jsonl` 至 `exports/` → 逐条复验事件契约 → 全程打印进度，末行打印 `验收通过`（依赖 T006~T010）
- [ ] T013 [US1] 执行 `uv run python scripts/run_minimal_chain.py` 与 `uv run pytest tests/integration/ -q`，修复至全绿

**Checkpoint**: US1 完成 = MVP 达成，可独立演示

---

## Phase 4: User Story 2 - 契约守卫 (Priority: P2)

**Goal**: 非法数据在入库/写入时被明确拒绝，永不落库

**Independent Test**: 单独运行 `uv run pytest tests/contract/ -q`

- [ ] T014 [P] [US2] 编写 `tests/contract/test_schema_guard.py`：缺必填字段的资产被拒、`asset_id` 格式不符被拒、非法 `type` 的事件被拒；每种拒绝后断言数据库无变化；断言错误信息含 JSON 路径（契约 `contracts/asset-event-schemas.md` 的错误格式）
- [ ] T015 [US2] 执行 `uv run pytest tests/contract/ -q` 修复至全绿；若发现 `orchestrator/store.py` 校验缺口，补齐缺口而非放宽测试

**Checkpoint**: US1、US2 均独立可用

---

## Phase 5: User Story 3 - 后续里程碑的接缝就位 (Priority: P3)

**Goal**: 后端可替换、存储单通路、导出可脱离数据库消费 —— 三处接缝被验证

**Independent Test**: 单独运行接缝测试，不改任何 Phase 2/3 代码

- [ ] T016 [US3] 编写 `tests/integration/test_backend_swap.py`：定义第二个 Mock 后端变体，仅通过替换注入参数跑通 4 回合链路并过契约校验；断言 `scripts/run_minimal_chain.py` 无需改动（注入点存在）
- [ ] T017 [P] [US3] 编写 `tests/contract/test_single_store_path.py`：静态扫描 `scripts/`、`tests/`、`orchestrator/`（除 `store.py`）不含 `sqlite3` import 与直连调用，断言唯一数据库通路为 `orchestrator/store.py`

**Checkpoint**: 全部用户故事独立可用

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 文档与最终验收

- [ ] T018 [P] 编写 `README.md`：三步上手（`uv sync` → `cp .env.example .env` → `uv run python scripts/run_minimal_chain.py`）+ 目录结构说明 + 指向 `mydocs/` 手册与宪章
- [ ] T019 全量验证：`uv run pytest -q` 全绿；最小链路连续两次运行做确定性比对；按 `specs/001-uv-m1-baseline/quickstart.md` 逐步走查
- [ ] T020 清理核对：`exports/` 与 `narrative_sim.db` 未入库；`git status` 干净；确认宪章七项门禁在最终代码上仍全部满足

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，立即开工
- **Foundational (Phase 2)**: 依赖 Phase 1 —— 阻塞所有用户故事
- **User Stories (Phase 3-5)**: 依赖 Phase 2；按 P1 → P2 → P3 顺序执行
- **Polish (Phase 6)**: 依赖所有用户故事完成

### User Story Dependencies

- **US1 (P1)**: Phase 2 完成后开工，不依赖其他故事
- **US2 (P2)**: Phase 2 完成后可开工（守卫测试针对 store，与 US1 无代码依赖）
- **US3 (P3)**: 依赖 US1 的 `run_minimal_chain.py`（接缝验证对象）

### Parallel Opportunities

- Phase 1：T003 可与 T001/T002 并行
- Phase 2：T004 ∥ T005（两张 Schema 不同文件）；T008 可与 T006/T007 并行
- Phase 4：T014 内部用例相互独立
- Phase 5：T016 ∥ T017（不同测试文件）

### Parallel Example: Phase 2

```bash
# 同时开工：
Task: "编写 schemas/asset.schema.json"
Task: "编写 schemas/event.schema.json"
Task: "实现 orchestrator/llm.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1: Setup
2. 完成 Phase 2: Foundational（关键阻塞点）
3. 完成 Phase 3: User Story 1
4. **STOP and VALIDATE**: 独立验收 US1（quickstart 三步）
5. 此时即为可演示的 MVP

### Incremental Delivery

1. Setup + Foundational → 基座就绪
2. + US1 → 独立验收 → MVP
3. + US2 → 独立验收（契约守卫全绿）
4. + US3 → 独立验收（接缝验证全绿）
5. 每个故事增量交付，不破坏前序故事

---

## Notes

- [P] 任务 = 不同文件、无依赖
- [Story] 标签用于 spec 追溯
- 先写测试并确认 FAIL，再实现（US1 的 T011 → T012）
- 每个 Checkpoint 停下来独立验收当前故事
- 提交节奏：每个任务或逻辑组一次提交，信息单一意图
