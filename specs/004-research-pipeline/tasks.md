# Tasks: 自动资产调研管线

**Input**: Design documents from `/specs/004-research-pipeline/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅（gptr-mcp server.py 已核实）、
data-model.md ✅、quickstart.md ✅；无 contracts/（两张契约不动）

**Tests**: 本特性包含测试任务 —— spec 要求离线 Mock 基线（FR-008）与 SC-004 全绿。
测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段。注意两个世界：本仓库代码（客户端）与
仓库外的 gptr-mcp 服务端（T002 spike 搭建，后续真机验收依赖它）。

## Phase 1: Setup

- [X] T001 [P] `.env.example` 增加客户端键位（含注释，不出现具体地址字面量）：
  `GPTR_MCP_URL`（未设=明确报错）、`RESEARCH_TIMEOUT_S`（默认 180）、
  `RESEARCH_DEDUP_THRESHOLD`（默认 0.85）
- [X] T002 Spike：搭建 gptr-mcp 服务端（仓库外，不产生本仓库代码改动）——
  在 `D:\kimicode_repos\projects\my-gpt-research\gptr-mcp` 建 venv，
  gpt-researcher 从本地 fork 路径安装（保留补丁），按 quickstart.md 0b 的
  环境变量启动；验证 `GET /health` 200 + streamable-http 端点可 initialize
  （失败则退 `MCP_TRANSPORT=sse` 并记录到 quickstart）；可选：跑一次最小
  deep_research 确认 SearXNG + DeepSeek 链路通（有 token 成本，可留到 T009）

---

## Phase 2: Foundational（阻塞所有故事）

- [X] T003 `uv add mcp`（官方 MCP 客户端包，pin 版本进 lock；原则 V）
- [X] T004 嵌入助手共享化：把 `_embedding_config` / `_build_embedding_model` /
  `EMBEDDING_DIM` 等常量从 `orchestrator/persona_tinytroupe.py` 移到新模块
  `orchestrator/embedding.py`，persona 适配器改为 import（行为不变）；
  `tests/contract/test_tinytroupe_embedding.py` 的 import 路径同步更新，
  003 既有 15 项测试保持全绿
- [X] T005 [P] `orchestrator/store.py` 增加只读方法 `list_assets(type: str) -> list[dict]`
  （原则 III：store 仍是唯一入口，仅多一个读方法），附离线测试

**Checkpoint**: 基础就绪 —— embedding.py 可独立 import，store 可按类型列资产

---

## Phase 3: User Story 1 - 查询词到入库资产 (Priority: P1) 🎯 MVP

**Goal**: 查询词经 gptr-mcp deep_research + chat_json 抽取，产出契约资产入库

**Independent Test**: 真机跑两个人物/场景查询词，库中资产契约校验通过、
`provenance.retriever="gptr-mcp(searxng)"`、sources 非空

### Tests for User Story 1（先写，确认失败）

- [X] T006 [US1] 新建 `tests/contract/test_research_pipeline.py`，mock 三层
  （MCP call_tool / llm.chat_json / 时间）：
  成功路径（context+source_urls → 草稿 → put_asset 被调、溯源字段填充正确、
  asset_id 形态 `^(char|prop|scene|epoch)_[a-z0-9_]+$`）；
  草稿不合契约 → 重试 1 次 → 仍失败则报错且 put_asset 零调用；
  source_urls 为空 → 拒绝入库；query 为空/纯空白 → 直接拒绝且不发起 MCP 调用

### Implementation for User Story 1

- [X] T007 [US1] 实现 `orchestrator/research.py`（依赖 T003-T005）：
  MCP 客户端封装（streamable-http 连接 `GPTR_MCP_URL`，call_tool 为可 mock 接缝，
  超时 `RESEARCH_TIMEOUT_S`）；管线 `research_asset(query, asset_type, store)`
  = deep_research → `llm.chat_json()` 按类型指引抽取 → asset_id/溯源填充
  （data-model.md 口径：retriever/model/researched_at/confidence/sources）→
  `store.put_asset()` 校验入库；抽取失败重试 1 次后干净报错
- [X] T008 [US1] 实现 `scripts/research_asset.py` CLI（`--query --type --db`），
  打印 asset_id 或明确错误；`GPTR_MCP_URL` 未设 → 明确提示缺失（FR-007）
- [X] T009 [US1] 真机验收（需 T002 服务端在线）：按 quickstart.md 场景 2 跑
  人物 + 场景两个查询词，确认入库资产契约通过、溯源完整（SC-001）

**Checkpoint**: US1 独立成立 —— 查询词到入库资产全链路可证

---

## Phase 4: User Story 2 - 入库前语义去重 (Priority: P2)

**Goal**: 同义资产重复调研时判重返回已有 asset_id，零新写入；嵌入不可用降级

**Independent Test**: 真机用同义不同文查询词再调研，库中该类资产数量不变

### Tests for User Story 2（先写，确认失败）

- [X] T010 [US2] 在 `tests/contract/test_research_pipeline.py` 增加去重用例
  （mock 嵌入调用）：余弦 ≥ 阈值 → 判重返回已有 asset_id 且 put_asset 零调用；
  < 阈值 → 正常入库；嵌入配置缺失/调用异常 → 降级 name 精确匹配 + 降级日志；
  阈值经 `RESEARCH_DEDUP_THRESHOLD` 环境变量可调

### Implementation for User Story 2

- [X] T011 [US2] 在 `orchestrator/research.py` 接入去重（依赖 T004、T005、T007）：
  入库前对 `name + appearance` 与同 type 库中资产（`list_assets`）做语义比对，
  比较文本与降级口径按 data-model.md「去重判定」
- [X] T012 [US2] 真机验收：按 quickstart.md 场景 3 跑同义查询，确认判重（SC-002）；
  嵌入服务停掉再跑，确认降级提示与精确匹配路径

**Checkpoint**: US1、US2 均独立成立

---

## Phase 5: User Story 3 - 外部故障隔离与配置可移植 (Priority: P3)

**Goal**: 服务不可达明确报错零写入；地址只走环境变量

**Independent Test**: 停掉 gptr-mcp 服务跑 CLI 明确报错、库中零新增；
unset `GPTR_MCP_URL` 提示缺配置

### Tests for User Story 3

- [X] T013 [US3] 在 `tests/contract/test_research_pipeline.py` 增加用例：
  `GPTR_MCP_URL` 未设 → 明确报错且不发起任何网络调用；
  MCP 连接失败/调用超时 → 明确报错且 put_asset 零调用；
  全仓库 grep 无硬编码服务端地址（`orchestrator/` 与 `scripts/`）

**Checkpoint**: 三个故事全部独立成立

---

## Phase 6: Polish & 全量验收

- [X] T014 全量离线回归 `uv run pytest -m "not real"` 全绿（SC-004：001/002/003 不回归）
- [X] T015 按 `specs/004-research-pipeline/quickstart.md` 四场景逐一验证
  （离线回归 / 真机调研 / 语义去重 / 故障隔离）
- [X] T016 本文件全部任务标记 [X]，提交（建议
  `feat(004): research pipeline via gptr-mcp service`）

---

## Dependencies & Execution Order

- Phase 1：T001 与 T002 可并行（不同世界：仓库内 vs 仓库外）
- Phase 2：T003 → T004（T003 无依赖；T004 触碰 003 文件，需先确认回归基线）；
  T005 可与 T003/T004 并行
- US1（Phase 3）依赖 Phase 2；T009 另依赖 T002 服务端在线
- US2（Phase 4）依赖 T007（管线存在才能接去重）
- US3（Phase 5）依赖 T008（CLI 存在才能做故障验收）
- Phase 6 依赖所有故事完成

### Parallel Opportunities

T001 ∥ T002；T005 ∥ (T003, T004)；同文件任务（research.py 的 T007/T011、
测试文件的 T006/T010/T013）严格串行。

## Implementation Strategy

MVP = Phase 1-3（US1）：查询词到入库资产全链路成立即可演示核心价值；
US2/US3 依次增量，每个故事完成后独立验收再继续。
T002（服务端 spike）建议最先做 —— 它不阻塞仓库内开发，但 T009 真机验收依赖它。
