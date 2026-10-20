# Phase 0 Research: MCP Server 协议封装

日期：2026-10-20。FastMCP 事实来自 005 实战经验 + gptr-mcp venv 源码核实；
orchestrator 复用面来自本仓库既有代码。

## R1: fastmcp 安装形态 — fastmcp-slim[server]（005 教训复用）

**Decision**: `uv add "fastmcp-slim[server]"`。

**Rationale**: 005 实测——fastmcp 4.x 拆分为 fastmcp-slim 核心 + server extra；
装裸 `fastmcp` 会在启动时报 `No module named 'mcp.server.request_state'`。
主项目已有 `mcp 2.3.0`（005 客户端依赖），与 fastmcp-slim[server] 的
mcp 2.x 要求一致，无版本冲突预期。

## R2: 模块布局与入口

**Decision**:
- `orchestrator/mcp_server.py`：FastMCP 实例 + 六个工具定义（薄封装），
  暴露 `build_server() -> FastMCP` 供测试与入口复用（手册命名沿用）
- `scripts/run_mcp_server.py`：启动入口，读环境变量后调 `mcp.run()`
- 传输：`MCP_TRANSPORT`（默认 `streamable-http`）、`MCP_HOST`
  （默认 127.0.0.1）、`MCP_PORT`（默认 8300）——FR-003；stdio 不做
- 启动零外部检查（Edge Case）：gptr-mcp/嵌入不在线不影响启动，
  工具调用时按各自口径报错/降级

**备选位置说明**: 放 orchestrator/ 因它是协议适配器而非业务；
SC-004 用 grep 限定该文件只允许 import orchestrator 既有模块、
插件包（gptr_deepseek_retriever）、fastmcp 与标准库。

## R3: 工具封装形态（FR-002/FR-004）

每个工具 = 类型标注 + docstring（fastmcp 自动出 schema）+ 一行 try：
- 编排异常（ResearchError / WorldConfigError / WorldSnapshotError /
  MissingEnvironmentError / KeyError / ValueError）→ `fastmcp.exceptions.ToolError
  (f"{错误类型}: {原因}")`——ToolError 的 message 会结构化回传客户端，
  不含堆栈；非预期异常同样兜成 ToolError（server 不崩）
- 返回值统一 dict：research_asset → {asset_id, deduplicated: bool}；
  create_world → {world_id, characters, location, action_count}；
  run_simulation → {run_id, event_count, ticks, cost_tokens?}；
  export_events → {path, count}；web_search → {results: [...]}；
  web_fetch → {title, content} 或错误

## R4: create_world / run_simulation 的编排接缝

**问题**: 006 的 `run_world()` 直接接收 character_ids/location_id 并从资产
组装配置；M5 的工具链要求 create_world 与 run_simulation 分步、经 world_id 衔接。

**Decision**（不碰 006 既有签名）:
- worlds.config 列（001 DDL 已存在，目前闲置）存世界定义 JSON：
  `{character_ids, location_id}`（由 create_world 写入）
- store.py 加 `put_world_config(world_id, config_json)` /
  `get_world_config(world_id) -> dict | None`（原则 III：仅多两个方法）
- create_world 工具：`build_scene_config()` 预检资产齐全（FR 缺口报错口径），
  写 worlds.config，返回摘要；重复 world_id 按 006 口径拒绝（除非显式 reset）
- run_simulation 工具：读 worlds.config → 调 006 `run_world()`
  （backend 参数：默认真后端，`backend="mock"` 供测试演示；resume 透传）

## R5: run_simulation 长调用超时口径（spec Assumptions 待定项）

**Decision**: 工具同步执行；文档化耗时预期（真后端每 tick 每角色 ≈ 1 次
LLM 调用 ≈ 15-30s），客户端侧 timeout 按 `120s + 60s × ticks` 估算配置。
server 不设硬性超时（长仿真合法）；MCP streamable-http 长连接由
fastmcp/uvicorn 默认承载（gptr-mcp 的 deep_research 分钟级调用已实证可行）。

**Alternatives considered**: 异步任务 + 轮询工具——超 scope
（spec 明确不做进度推送），后续特性再评。

## R6: 离线测试策略（FR-007）

**Decision**: fastmcp 进程内客户端（`Client(FastMCPTransport(mcp))` 形态，
fastmcp/client/client.py:94 已核实存在）对 `build_server()` 实例直接调用：
- 六工具 list_tools 可见且带 schema
- research_asset：mock call_tool/chat_json（004 既有接缝）全链
- create_world/run_simulation(mock)/export_events：真实引擎 + MockBackend
  （006 离线基线）+ tmp_path DB，全链产出与 CLI 形态一致（SC-001）
- 错误三类：坏参数/缺前置/服务不可达 → ToolError 结构化（SC-002）
- web_search/web_fetch：mock httpx（005 既有接缝）
- 零网络、零外部进程

## R7: 依赖与回归面

- 新增依赖仅 `fastmcp-slim[server]`（uv，原则 V）；mcp 2.3.0 已在 lock
- store.py 仅加两个 world config 方法；006 的 run_world / world.py 零改动
- 入口脚本与 server 模块均为新增文件，既有文件零触碰（除 store 两方法）
- M1-M6 回归由既有 97 项 + 新增用例兜底
