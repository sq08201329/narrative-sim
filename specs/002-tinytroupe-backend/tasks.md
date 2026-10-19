# Tasks: TinyTroupe 真后端接入（M2）

**Input**: Design documents from `specs/002-tinytroupe-backend/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: 包含测试任务 —— plan D9 已定测试策略（离线单元测试进回归套件 + `real` 标记在线验收）。

**Organization**: 任务按用户故事分组，每个故事可独立实现、独立验收。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1/US2/US3，对应 spec.md）
- 所有任务含确切文件路径

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 依赖锁定与配置文件

- [ ] T001 执行 `uv add "tinytroupe @ git+https://github.com/microsoft/TinyTroupe.git@a6244b358a1fe1c71bf751f7ba0f8dfa368ec5a4"`，核对 `pyproject.toml` 与 `uv.lock` 均含该 commit pin；GitHub 不通时按手册 4.2 用 Gitee 镜像先把仓库克隆到本地再 `uv add` 本地路径调试，但 pyproject 最终保留带 commit 的 git URL
- [ ] T002 [P] 创建 `config.ini`（项目根）：`[OpenAI] api_type=openai`、`model=deepseek-flash`；`[ActionGenerator] max_attempts=2`、`enable_quality_checks=True`、`continue_on_failure=True`；`[Simulation] parallel_agent_actions=False`（键表见 data-model.md）
- [ ] T003 [P] 更新 `.env.example`：追加 `OPENAI_API_KEY=` 与 `OPENAI_BASE_URL=https://api.deepseek.com`（TinyTroupe 经 openai SDK 读取，见 research.md D6）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 存储扩展与测试标记 —— 阻塞所有用户故事

**⚠️ CRITICAL**: 本阶段未完成前，任何用户故事不得开工

- [ ] T004 在 `orchestrator/store.py` 新增 `update_run_cost(run_id: str, total_tokens: int) -> None`：更新 `runs.token_cost` 列；run_id 不存在时抛明确错误（宪章原则 III：唯一入口内扩展）
- [ ] T005 [P] 在 `pyproject.toml` 注册 pytest 标记：`[tool.pytest.ini_options]` 加 `markers = ["real: 需要真实 LLM 密钥的在线验收用例"]`
- [ ] T006 [P] 更新 `.gitignore`：追加 `openai_api_cache.json` 与 `tinytroupe.*.log`（TinyTroupe 缓存/日志写 cwd，见 research.md D8 坑 3）

**Checkpoint**: 基座就绪，用户故事可开工

---

## Phase 3: User Story 1 - 真实角色心智驱动仿真 (Priority: P1) 🎯 MVP

**Goal**: 真后端 4 回合产出 ≥5 条契约合法事件；M1 不回归

**Independent Test**: `uv run pytest tests/contract/test_tinytroupe_backend.py -q` 全绿（离线）+
有密钥时 `uv run python scripts/run_real_chain.py` 输出「验收通过」

### Tests for User Story 1

> **NOTE: 先写测试并确认 FAIL，再实现**

- [ ] T007 [US1] 编写 `tests/contract/test_tinytroupe_backend.py`（monkeypatch 隔离 LLM，离线可跑）：动作映射 `TALK→dialogue` / `THINK→inner_voice` / `DONE→丢弃`；`emotion` 取自 `cognitive_state.emotions`；同一 `asset_id` 只构建一次 TinyPerson（缓存复用）；缺 `OPENAI_API_KEY` / `OPENAI_BASE_URL` 时抛指明变量名的错误；`act` 终极失败重试 3 次后抛明确错误且不产出事件。先运行确认 FAIL

### Implementation for User Story 1

- [ ] T008 [US1] 实现 `orchestrator/persona_tinytroupe.py`：`TinyTroupeBackend` 实现 `PersonaBackend` Protocol —— 环境预检通过后才懒 import tinytroupe；`TinyPerson(name=asset_id)` + `include_persona_definitions()`（`speech_style`→`style`）；`dict[asset_id, TinyPerson]` 缓存；每回合 `listen(visible_state 摘要)` + `act(return_actions=True)`；按映射表转换，DONE 丢弃（依赖 T007 先 FAIL）
- [ ] T009 [US1] 实现 `scripts/run_real_chain.py`：cwd 守卫（`Path.cwd()` 必须是项目根，否则明确报错退出非 0）；环境预检；复用 `scripts/run_minimal_chain.py` 的资产定义与链路流程（`from run_minimal_chain import ...`，sys.path[0] 即 scripts/）；后端注入 `TinyTroupeBackend`；运行前 `client().reset_cost_stats()`、结束后 `get_cost_stats()["total_tokens"]` 经 `store.update_run_cost()` 落库（依赖 T004、T008）
- [ ] T010 [US1] 离线验证：`uv run pytest -q` 全绿（含新单元测试，real 用例 skip）+ `uv run python scripts/run_minimal_chain.py` 不回归
- [ ] T011 [US1] 在线验收：`.env` 配好密钥后 `uv run python scripts/run_real_chain.py` → ≥5 条事件全过契约、输出「验收通过」、第 2 回合起内容承接前序回合（SC-002 抽查）；无密钥时记录为人工验收待办，不得伪造通过

**Checkpoint**: US1 完成 = MVP 达成

---

## Phase 4: User Story 2 - 后端一键切换 (Priority: P2)

**Goal**: 两条链路仅差后端注入；Mock 链路在无密钥环境照常通过

**Independent Test**: `uv run pytest tests/integration/test_chain_parity.py -q` 单独全绿

- [ ] T012 [US2] 编写 `tests/integration/test_chain_parity.py`：断言 `run_real_chain.py` 复用 `run_minimal_chain.py` 的资产定义与流程（无重复资产字面量）；subprocess 清空 `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` 环境跑 Mock 链路仍验收通过（US2 AC2）
- [ ] T013 [US2] 执行 `uv run pytest tests/integration/ -q` 修复至全绿

**Checkpoint**: US1、US2 均独立可用

---

## Phase 5: User Story 3 - 成本可审计 (Priority: P3)

**Goal**: token 成本按 run_id 落库可查；Mock 不产生虚假记账

**Independent Test**: `uv run pytest tests/contract/test_cost_tracking.py -q` 单独全绿

- [ ] T014 [US3] 编写 `tests/contract/test_cost_tracking.py`：monkeypatch cost stats 后断言真链路路径会把 `total_tokens` 写入 `runs.token_cost`（经 `update_run_cost`）；Mock 链路运行后 `token_cost` 保持 0；`update_run_cost` 对不存在 run_id 抛错
- [ ] T015 [US3] 执行 `uv run pytest tests/contract/ -q` 修复至全绿；在线验收（T011）中确认真实运行后 `token_cost` 非零

**Checkpoint**: 全部用户故事独立可用

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 文档与最终验收

- [ ] T016 [P] 更新 `README.md`：真后端链路用法（密钥配置、cwd 要求、`config.ini` 作用）+ 在线/离线两条验证路径
- [ ] T017 全量验证：`uv run pytest -q` 全绿（real 标记正确 skip）；M1 链路两次运行；按 `specs/002-tinytroupe-backend/quickstart.md` 逐步走查（含负向 cwd 验证）；复核宪章七项门禁
- [ ] T018 清理核对：`openai_api_cache.json` / `tinytroupe.*.log` / `.env` 均未入库；`git status` 干净

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖；T001 需网络（GitHub/Gitee）
- **Foundational (Phase 2)**: 依赖 Phase 1 —— 阻塞所有用户故事
- **User Stories (Phase 3-5)**: 依赖 Phase 2；按 P1 → P2 → P3 顺序
- **Polish (Phase 6)**: 依赖所有用户故事完成

### User Story Dependencies

- **US1 (P1)**: Phase 2 完成后开工，不依赖其他故事
- **US2 (P2)**: 依赖 US1 的 `run_real_chain.py`（对比对象）
- **US3 (P3)**: 依赖 US1 的成本记账代码路径（测试对象）

### Parallel Opportunities

- Phase 1：T001 ∥ T002 ∥ T003（不同文件）
- Phase 2：T004 ∥ T005 ∥ T006（不同文件）
- US1 内：T007（测试）→ T008/T009（实现）→ T010（离线）→ T011（在线）

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 + Phase 2
2. 完成 Phase 3: US1（离线全绿即 MVP；在线验收 T011 依赖密钥可用性）
3. **STOP and VALIDATE**：quickstart 离线路径全过
4. 之后按 US2 → US3 增量推进

### 风险预案

- T001 网络受阻：按手册 4.2 Gitee 镜像克隆 + 本地路径 `uv add` 调试，
  pyproject 仍写带 commit 的 git URL（T001 验收口径不变）
- T011 无密钥：标记为人工验收待办并在任务旁注明，不得跳过 US1 其他验收

---

## Notes

- [P] 任务 = 不同文件、无依赖
- [Story] 标签用于 spec 追溯
- 先写测试并确认 FAIL，再实现（T007 → T008/T009）
- 每个 Checkpoint 停下来独立验收当前故事
- 提交节奏：每个任务或逻辑组一次提交，信息单一意图
