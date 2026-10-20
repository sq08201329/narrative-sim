# Tasks: 恢复语义记忆（本地嵌入服务接入）

**Input**: Design documents from `/specs/003-semantic-memory-restore/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅（探针实测结论）、data-model.md ✅、
quickstart.md ✅；无 contracts/（两张契约不动）

**Tests**: 本特性包含测试任务 —— spec 明确要求离线单测（US2 独立测试）与召回探针
（US1-AC2），且 SC-004 要求离线套件全绿。测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；全部实现改动集中在
`orchestrator/persona_tinytroupe.py`（原则 II），因此同文件任务严格串行、不标 [P]。

## Phase 1: Setup

- [ ] T001 `.env.example` 增加嵌入键位（含注释说明，不出现具体地址字面量）：
  `EMBEDDING_API_BASE`（未设=降级）、`EMBEDDING_MODEL`（默认 `eg2-text-270m.litertlm`）、
  `EMBEDDING_TIMEOUT_S`（默认 10）、`EMBEDDING_MAX_CHARS`（默认 2000）

---

## Phase 2: Foundational（嵌入子类，阻塞所有故事）

**Purpose**: 嵌入客户端子类是 US1 真实模式与 US2 降级判定的共同基础

- [ ] T002 在 `orchestrator/persona_tinytroupe.py` 增加嵌入配置读取：从环境变量构造
  配置（api_base / model / timeout_s / max_chars，默认值与校验规则见
  data-model.md「嵌入服务描述」表）；`EMBEDDING_API_BASE` 未设时返回 None
- [ ] T003 在 `orchestrator/persona_tinytroupe.py` 实现嵌入子类（继承 llama-index
  `OpenAIEmbedding`）：`model_name=` 传参绕枚举白名单（research.md R1）；
  `_get_text_embedding(s)` 加 `task: search result | text: ` 前缀、
  `_get_query_embedding` 加 `task: search query | text: ` 前缀（R2）；
  空/纯空白文本不发请求直接返回 768 维零向量；超长按 max_chars 截断；
  `timeout=timeout_s`、`max_retries=1`；全异常拦截返回零向量 + 降级日志只打一次（R4）

**Checkpoint**: 子类可独立实例化（指向任意 OpenAI 兼容端点），不触碰 TinyTroupe 全局状态

---

## Phase 3: User Story 1 - 语义检索恢复 (Priority: P1) 🎯 MVP

**Goal**: 嵌入服务在线时，语义记忆写入与召回真正经嵌入服务向量化

**Independent Test**: `uv run python scripts/probe_embedding_service.py` 退出码 0，
相关文档召回余弦高于无关文档；真链路输出 semantic_mode=real 且验收通过

### Tests for User Story 1（先写，确认失败）

- [ ] T004 [US1] 新建 `tests/unit/test_persona_tinytroupe_embedding.py`：mock httpx 层
  验证子类行为 —— 文档/查询请求体分别带正确任务前缀与 `model` 字段；空文本不发请求；
  超长文本截断到 `EMBEDDING_MAX_CHARS`；异常/超时返回 768 维零向量且不抛出

### Implementation for User Story 1

- [ ] T005 [US1] 在 `orchestrator/persona_tinytroupe.py` 实现预检与真实模式接线
  （依赖 T002、T003）：真后端构造（`person_cls is None`）且 `EMBEDDING_API_BASE` 已设时，
  `GET {api_base}/models`（超时 5s）返回含 `EMBEDDING_MODEL` 且一次最小 embeddings
  调用成功 → import tinytroupe 后用子类实例覆盖 `Settings.embed_model`
  （R3：import 时默认实例会指向 DeepSeek，必须在首个 TinyPerson 创建前覆盖）；
  TinyPerson 不再注入 `_local_semantic_memory()`；后端暴露只读 `semantic_mode`
  属性（`"real"`）
- [ ] T006 [US1] 扩展 `scripts/probe_embedding_service.py` 为完整召回探针（US1-AC2）：
  写入「相关文档」+ 若干干扰文档 → 经查询前缀检索，相关文档余弦高于无关文档，
  不满足则退出码非 0（不调 LLM，可作为验收门槛）
- [ ] T007 [US1] 在线验收：启动嵌入服务，`uv run pytest tests/unit/test_persona_tinytroupe_embedding.py`
  全绿；`uv run python scripts/probe_embedding_service.py` 退出码 0；
  `uv run python scripts/run_real_chain.py` 验收通过（≥5 事件、契约全过）

**Checkpoint**: US1 独立成立 —— 真实语义模式可证、可用

---

## Phase 4: User Story 2 - 服务离线时优雅降级 (Priority: P2)

**Goal**: 嵌入服务不可用 → 自动回退 002 本地列表行为，仿真照常完成并明确提示

**Independent Test**: 嵌入服务停止状态下 `uv run python scripts/run_real_chain.py`
退出码 0、输出含降级提示；离线单测模拟不可达验证降级路径

### Tests for User Story 2（先写，确认失败）

- [ ] T008 [US2] 在 `tests/unit/test_persona_tinytroupe_embedding.py` 增加降级用例：
  mock `/models` 不可达 / 模型名不在返回列表 / 最小调用抛异常 →
  均判定降级；降级后 `semantic_mode` 以 `"degraded: <原因>"` 形式给出原因

### Implementation for User Story 2

- [ ] T009 [US2] 在 `orchestrator/persona_tinytroupe.py` 实现降级接线（依赖 T005）：
  预检任一失败或 `EMBEDDING_API_BASE` 未设 → 沿用 002 的
  `_local_semantic_memory()` 注入路径，`semantic_mode = "degraded: <原因>"`；
  运行中嵌入失败由 T003 零向量拦截兜底（US2-AC2，不导致仿真崩溃）
- [ ] T010 [US2] `scripts/run_real_chain.py` 打印后端 `semantic_mode`
  （real / degraded 及原因）；在线验收：停掉嵌入服务跑真链路，退出码 0、
  输出含降级提示；恢复服务再跑确认回到 real

**Checkpoint**: US1、US2 均独立成立 —— 服务在/不在都验收通过

---

## Phase 5: User Story 3 - 配置可移植 (Priority: P3)

**Goal**: 服务地址只走环境变量，代码零硬编码

**Independent Test**: 用环境变量指向 mock 嵌入端点，链路使用新地址；
未设变量走降级路径（US3-AC1 选定口径）

### Tests for User Story 3

- [ ] T011 [US3] 在 `tests/unit/test_persona_tinytroupe_embedding.py` 增加配置用例：
  未设 `EMBEDDING_API_BASE` → 直接降级不发起任何网络调用；指向 mock 端点的
  环境变量被实际用于预检与嵌入请求；全仓库 grep 无硬编码服务地址字面量
  （`127.0.0.1:9379` 之类不得出现在 `orchestrator/` 与 `scripts/run_real_chain.py`）

**Checkpoint**: 三个故事全部独立成立

---

## Phase 6: Polish & 全量验收

- [ ] T012 全量离线回归 `uv run pytest -m "not real"` 全绿（SC-004：001/002 不回归）
- [ ] T013 按 `specs/003-semantic-memory-restore/quickstart.md` 四场景逐一验证
  （探针 / 真链路 real / 真链路降级 / 离线回归）
- [ ] T014 本文件全部任务标记 [X]，提交（建议
  `feat(003): restore semantic memory via local embedding service`）

---

## Dependencies & Execution Order

- Phase 1（T001）无依赖，可随时做
- Phase 2（T002→T003 串行）阻塞所有故事
- US1（Phase 3）依赖 Phase 2；US2（Phase 4）依赖 T005（预检存在才能接降级）；
  US3（Phase 5）依赖 T009（降级路径存在才能测）
- Phase 6 依赖所有故事完成

### Parallel Opportunities

本特性核心实现集中在单一文件 `orchestrator/persona_tinytroupe.py`，
实现任务全部串行；仅 T001（.env.example）与 T006（探针脚本）与其他任务无文件冲突，
可分别与 T002/T005 并行。

## Implementation Strategy

MVP = Phase 1-3（US1）：真实语义模式成立即可演示核心价值；
US2/US3 依次增量，每个故事完成后独立验收再继续。
