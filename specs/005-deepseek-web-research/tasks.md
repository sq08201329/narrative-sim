# Tasks: GPT-Researcher 接入 DeepSeek 检索腿

**Input**: Design documents from `/specs/005-deepseek-web-research/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅（fork 机制行号级证据）、
data-model.md ✅、quickstart.md ✅；无 contracts/（两张契约不动）

**Tests**: 本特性包含测试任务 —— spec 要求离线 Mock 基线（FR-008/FR-009）与
SC-004 全绿。测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段。注意两个世界：本仓库（插件包 + 一处
research.py 改动）与仓库外的 gptr-mcp 服务端（装插件 + RETRIEVER 换腿）。

## Phase 1: Setup

- [X] T001 [P] 创建插件包骨架 `plugins/gptr-deepseek-retriever/`：
  `pyproject.toml`（name `gptr-deepseek-retriever`，依赖仅 httpx，
  entry-point 组 `gpt_researcher.retrievers` 注册 `deepseek`）、
  `gptr_deepseek_retriever/__init__.py`（导出占位）
- [X] T002 [P] 主项目引入插件 path 依赖：`uv add --editable
  ./plugins/gptr-deepseek-retriever`（pyproject `[tool.uv.sources]` 记录）；
  `.env.example` 加 `GPTR_MCP_RETRIEVER_LABEL`（默认 `gptr-mcp(deepseek-search)`）

---

## Phase 2: Foundational（工具函数，阻塞所有故事）

- [X] T003 实现 `plugins/gptr-deepseek-retriever/gptr_deepseek_retriever/client.py`
  （FR-009）：`web_search(query, count=8, need_content=True) -> list[dict]`
  与 `web_fetch(url) -> dict | None`——httpx + Bearer（`DEEPSEEK_API_KEY`，
  缺失打印警告返回空）、端点由 `DEEPSEEK_SEARCH_BASE_URL` 派生（默认官方地址）；
  429/5xx 退避 2s/4s 重试 ≤`DEEPSEEK_SEARCH_RETRIES`（默认 2）；
  401/402 打印原因；query 截断 128；超时 30s；任何路径不抛异常
  （返回 [] 或 None）

**Checkpoint**: 两个工具函数可独立 import 调用（mock 下）

---

## Phase 3: User Story 1 - DeepSeek 检索腿跑通调研入库 (Priority: P1) 🎯 MVP

**Goal**: gptr-mcp 换 DeepSeek 腿后，查询词 → 契约资产入库全流程跑通

**Independent Test**: SearXNG 停开、真机跑人物+场景查询词，资产契约通过、
sources 非空、retriever 为 `gptr-mcp(deepseek-search)`

### Tests for User Story 1（先写，确认失败）

- [X] T004 [US1] 新建 `tests/contract/test_gptr_deepseek_retriever.py`，
  mock HTTP 层：
  工具函数——search 成功映射/无结果 []/429→重试→成功/429 持续→[]/
  401、402→[]+警告/响应非 dict→[]/query 截断/fetch 成功与 404→None；
  retriever 类——`requires_scraping is False` 显式声明、content→raw_content、
  summary 垫底、皆空丢弃、body 映射（summary 优先）、
  `search(max_results=)` 同步签名

### Implementation for User Story 1

- [X] T005 [US1] 实现 `plugins/gptr-deepseek-retriever/gptr_deepseek_retriever/deepseek.py`
  （依赖 T003）：`DeepSeekSearchRetriever` 鸭子类型契约
  （`__init__(query, headers=None, query_domains=None)` + 同步
  `search(max_results=10)`），复用 client.py 两个工具函数；
  补抓逻辑：content 与 summary 皆空且 rerank_score ≥1.5 的条目按分数降序
  Fetch ≤`DEEPSEEK_FETCH_MAX`（默认 2），失败回退/丢弃；
  `__init__.py` 导出类与两个工具函数
- [X] T006 [US1] Spike（仓库外）：gptr-mcp venv 安装插件
  `pip install D:\...\narrative-sim\plugins\gptr-deepseek-retriever`，
  以 `RETRIEVER=deepseek` 启动服务，确认不报 unknown retriever + /health 200；
  `RETRIEVER=deepseek` 未装插件时的报错形态记录到 quickstart（US2-AC2）
- [X] T007 [US1] 真机验收（SearXNG 停开）：按 quickstart.md 场景 4 跑
  人物 + 场景查询词，确认契约资产入库、sources 非空、
  `provenance.retriever="gptr-mcp(deepseek-search)"`（SC-001）

**Checkpoint**: US1 独立成立 —— DeepSeek 检索腿全链路可证

---

## Phase 4: User Story 2 - 检索腿可切换、溯源如实 (Priority: P2)

**Goal**: 检索腿 = 服务端 env 一次切换；客户端溯源标签如实记录

**Independent Test**: searx 腿重启服务确认 004 路径行为不变；
切换前后入库资产的 retriever 标识各自正确

### Tests for User Story 2（先写，确认失败）

- [X] T008 [US2] 在 `tests/contract/test_research_pipeline.py` 增加用例：
  `GPTR_MCP_RETRIEVER_LABEL` 未设 → retriever 默认
  `gptr-mcp(deepseek-search)`；显式设为 `gptr-mcp(searxng)` → 入库资产
  retriever 随之变化（mock call_tool 路径）

### Implementation for User Story 2

- [X] T009 [US2] `orchestrator/research.py`：`_compose_asset` 的
  `provenance.retriever` 改为读 `GPTR_MCP_RETRIEVER_LABEL`
  （默认 `gptr-mcp(deepseek-search)`）；gptr-mcp call_tool 路径其余行为不变；
  确认 004 既有测试按新默认值更新后全绿
- [X] T010 [US2] searx 腿回归（可选真机，视 360search 限流状态）：
  `RETRIEVER=searx` + SearXNG 在线时确认服务正常；记录结果到 quickstart

**Checkpoint**: US1、US2 均独立成立

---

## Phase 5: User Story 3 - 计费与故障语义 (Priority: P3)

**Goal**: 补抓闸门、重试上限、空结果闭环全部可证

**Independent Test**: 离线用例覆盖；真机无结果查询明确失败零写入

### Tests for User Story 3（大部分随 T004 落地）

- [X] T011 [US3] 补全 `tests/contract/test_gptr_deepseek_retriever.py`：
  补抓触发条件（皆空+高分才抓、上限约束、失败回退摘要、摘要也无丢弃）；
  插件缺 key → `search()` 返回 [] 不抛；并发安全（无实例可变状态断言）

**Checkpoint**: 三个故事全部独立成立

---

## Phase 6: Polish & 全量验收

- [X] T012 全量离线回归 `uv run pytest -m "not real"` 全绿（SC-004）
- [X] T013 全链路同义去重（SC-002，关闭 004 T017）：嵌入服务在线 +
  DeepSeek 腿，同义查询重复调研命中已有资产、库中数量为 1
- [X] T014 按 quickstart.md 场景 1-6 逐一验证
- [X] T015 本文件全部任务标记 [X]，提交（建议
  `feat(005): gptr deepseek retriever plugin + web_search/web_fetch tools`）

---

## Dependencies & Execution Order

- Phase 1：T001 ∥ T002（T002 依赖 T001 的包存在，顺序执行更稳）
- Phase 2（T003）阻塞 US1 的 T005（retriever 复用 client）
- US1（Phase 3）：T004 与 T003 可并行（测试 mock 先行）；T006 依赖 T005；
  T007 依赖 T006
- US2（Phase 4）：T009 改动小但触碰 004 断言默认值，需在 T004-T007 稳定后做
- US3（Phase 5）依赖 T005
- Phase 6：T013 依赖 T007（DeepSeek 腿在线）

### Parallel Opportunities

T001 ∥ T002 外的实现工作集中在插件包两个文件与两个测试文件，
T004（写测试）与 T003（写 client）可并行；其余串行。

## Implementation Strategy

MVP = Phase 1-3（US1）：DeepSeek 检索腿全链路成立即交付核心价值；
US2/US3 增量收口；T013 顺带关闭 004 遗留 T017。

---

## Phase 7: Convergence

- [ ] T016 360search 限流恢复后，以 `RETRIEVER=searx` 重启 gptr-mcp 并跑通一次调研，验证 searx 腿在 005 插件安装后仍正常（US2/AC1 的 searx 侧 live 验证） per US2/AC1 (partial)
