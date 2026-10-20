# Tasks: MCP Server 协议封装

**Input**: Design documents from `/specs/007-mcp-server/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅（fastmcp 形态已实测）、
data-model.md ✅、quickstart.md ✅；无 contracts/（两张契约不动）

**Tests**: 本特性包含测试任务 —— spec 要求离线覆盖六工具（FR-007）与
SC-003 全绿。测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；实现集中在新模块
`orchestrator/mcp_server.py`，同文件任务严格串行。

## Phase 1: Setup

- [X] T001 `uv add "fastmcp-slim[server]"`（005 实测形态）；验证
  `from fastmcp import FastMCP` 可 import 且既有 97 项离线测试不回归

---

## Phase 2: Foundational（阻塞所有故事）

- [X] T002 [P] `orchestrator/store.py` 增加 `put_world_config(world_id,
  config_json)` 与 `get_world_config(world_id) -> dict | None`
  （启用 worlds.config 列；原则 III：仅多两个方法），附离线测试
  （写读往返 / 无记录返回 None / 覆盖重写）

**Checkpoint**: worlds.config 读写就绪

---

## Phase 3: User Story 1 - 调研-仿真闭环 (Priority: P1) 🎯 MVP

**Goal**: 进程内 MCP 客户端调四工具完成 调研→组世界→跑仿真→导出 全链

**Independent Test**: 离线全链产出与 CLI 形态一致（事件契约 100% 通过）

### Tests for User Story 1（先写，确认失败）

- [X] T003 [US1] 新建 `tests/contract/test_mcp_server.py`（fastmcp 进程内
  客户端 + tmp DB + 004/006 mock 接缝）：
  list_tools 六工具可见且带 schema；全链 research_asset（mock 调研接缝）
  → create_world → run_simulation（mock 后端，真实引擎）
  → export_events——各步返回含衔接标识、事件契约全过、导出文件生成；
  SC-004 grep：mcp_server.py 只允许 import orchestrator 既有模块 /
  gptr_deepseek_retriever / fastmcp / 标准库

### Implementation for User Story 1

- [X] T004 [US1] 实现 `orchestrator/mcp_server.py`（依赖 T001、T002）：
  `build_server() -> FastMCP` + 六个工具薄封装（签名与返回口径见
  data-model.md）；create_world 预检资产缺口 + worlds.config 读写 +
  reset 口径；run_simulation 读 config 调 006 run_world
  （backend/resume 透传）；错误统一兜为 ToolError（`{类型}: {原因}`）
- [X] T005 [US1] 实现 `scripts/run_mcp_server.py`：读
  MCP_TRANSPORT（默认 streamable-http）/ MCP_HOST（默认 127.0.0.1）/
  MCP_PORT（默认 8300）后 `mcp.run()`；启动零外部检查

**Checkpoint**: US1 独立成立 —— 离线全链可证

---

## Phase 4: User Story 2 - 错误如实传递 (Priority: P2)

**Goal**: 坏参数/缺前置/服务不可达均返回结构化可读错误，server 存活

**Independent Test**: 三类错误场景进程内验证，错误可读、后续调用正常

### Tests for User Story 2（先写，确认失败）

- [X] T006 [US2] 在 `tests/contract/test_mcp_server.py` 增加：
  空 query / 非法 asset_type → ToolError 且无外部调用；
  不存在 world_id 调 run_simulation → 明确"世界不存在"错误；
  resume 无快照 → 明确错误；调研服务不可达（mock call_tool 抛
  ConnectionError）→ 调研服务故障说明；重复 create_world 无 reset →
  拒绝；全部场景后可继续正常调用

**Checkpoint**: US1、US2 均独立成立

---

## Phase 5: User Story 3 - Web 工具直调 (Priority: P3)

**Goal**: web_search / web_fetch 经 MCP 直调，结构与错误语义正确

**Independent Test**: mock httpx 调两工具，返回结构与失败说明可读

### Tests for User Story 3（随 T003/T006 落地，此处确认完整）

- [X] T007 [US3] 确认 `tests/contract/test_mcp_server.py` 覆盖：
  web_search 返回结构化条目（title/url/summary）、无结果空列表；
  web_fetch 成功返回 {title, content}、不可抓返回可读失败说明

**Checkpoint**: 三个故事全部独立成立

---

## Phase 6: Polish & 全量验收

- [X] T008 全量离线回归 `uv run pytest -m "not real"` 全绿（SC-003）
- [X] T009 真机冒烟：启动 `scripts/run_mcp_server.py`，fastmcp Client 经
  streamable-http list_tools + 调 web_search（真 API）+ run_simulation
  （mock 后端）验证传输层；按 quickstart.md 场景 4 验证错误语义
- [X] T010 本文件全部任务标记 [X]，提交（建议
  `feat(007): mcp server protocol layer (M5)`）

---

## Dependencies & Execution Order

- Phase 1（T001）无依赖，最先做
- Phase 2（T002）与 T003（写测试）可并行
- US1（Phase 3）依赖 T001/T002；T004 → T005
- US2/US3（Phase 4/5）依赖 T004（工具存在才能测错误与直调）
- Phase 6 依赖所有故事

### Parallel Opportunities

T002 ∥ T003；mcp_server.py 上的 T004/T006/T007 严格串行。

## Implementation Strategy

MVP = Phase 1-3（US1）：离线全链成立即交付核心价值；
US2/US3 为同文件增量，一并收口；真机冒烟（T009）只验证传输层与
错误语义，不重复真后端仿真（006 已验收）。
