# Feature Specification: MCP Server 协议封装

**Feature Branch**: `007-mcp-server`

**Created**: 2026-10-20

**Status**: Draft

**Input**: User description: "M5 MCP Server：用 FastMCP 把已验收的能力封装为 MCP 工具
——research_asset（调研入库）/ create_world（组装世界）/ run_simulation（跑仿真，
含断点续跑）/ export_events（导出事件流），顺带暴露 005 的 web_search / web_fetch；
只做协议封装，业务全在 orchestrator；LLM 客户端（Kimi/Claude 等）可经 MCP 直接
发起调研与仿真；离线可测；M1-M4/005 不回归。（mydocs 手册 M5 节仅作参考。）"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - LLM 客户端经 MCP 完成调研-仿真闭环 (Priority: P1)

LLM 客户端连接 MCP server 后，能依次调用工具完成：
调研资产 → 组装世界 → 跑仿真 → 导出事件流，
每一步的产出与对应 CLI 的结果一致（同一套 orchestrator 业务逻辑）。

**Why this priority**: 这是本特性的全部价值 —— 目前所有能力只有 CLI 入口、
只能人手动发起；MCP 是"谁发起"问题的答案：LLM 客户端可直接驱动全流程。

**Independent Test**: 以 MCP 客户端（进程内或 stdio）依次调四个工具，
验证调研入库、世界登记、仿真事件、导出文件与 CLI 形态一致。

**Acceptance Scenarios**:

1. **Given** MCP server 运行、客户端已连接，**When** 客户端列出工具，
   **Then** 六个工具全部可见且带参数 schema（客户端可据此构造调用）
2. **Given** 调研后端可用，**When** 客户端依次调用
   research_asset → create_world → run_simulation → export_events，
   **Then** 资产入库、世界登记、事件流产出且契约校验通过、导出文件生成，
   各步返回结果包含后续步骤所需的标识（asset_id / world_id / run_id / 路径）

---

### User Story 2 - 错误如实传递 (Priority: P2)

工具调用失败时（参数非法、世界不存在、外部服务不可达、LLM 密钥缺失），
客户端收到的是结构化、可读的错误信息，而不是服务器崩溃或含糊的堆栈。

**Why this priority**: MCP 客户端是 LLM——错误信息就是它的排障依据；
含糊或缺失的错误会让客户端陷入盲目重试（每一次都是成本）。

**Independent Test**: 以坏参数/缺前置/服务离线三类场景调用工具，
验证错误结构化、原因可读、server 进程存活。

**Acceptance Scenarios**:

1. **Given** 客户端用空查询词或不支持的资产类型调 research_asset，
   **Then** 返回明确参数错误，不产生任何外部调用
2. **Given** 客户端对不存在的 world_id 调 run_simulation，
   **Then** 返回"世界不存在/无快照"类明确错误，server 可继续服务后续调用
3. **Given** 调研服务不可达，**When** 调 research_asset，
   **Then** 返回调研服务故障的明确说明（与 CLI 同口径），不表现为服务器异常

---

### User Story 3 - Web 工具直调 (Priority: P3)

客户端可不经调研管线，直接调用 web_search / web_fetch 做即席检索与抓取，
返回结构化结果（标题/URL/摘要或正文）。

**Why this priority**: 005 已把两个函数做成独立工具（FR-009 的既定用途）；
它们是 LLM 客户端最常用的即席能力，封装成本几乎为零。

**Independent Test**: 离线 mock 调用两个工具，验证返回结构与错误语义
（无结果返回空、失败返回可读说明）。

**Acceptance Scenarios**:

1. **Given** DeepSeek 密钥配置，**When** 客户端调 web_search，
   **Then** 返回结构化条目列表（标题/URL/摘要），无结果时为空列表
2. **Given** 目标页不可抓取，**When** 客户端调 web_fetch，
   **Then** 返回可读的失败说明而非异常

---

### Edge Cases

- run_simulation 是长调用（真后端每回合一次 LLM 调用）：超时口径需明确
  （客户端可配置，默认按回合数线性放大）
- 同一 world_id 重复 create_world：按 006 口径拒绝或显式重置
- run_simulation 指定 resume 但无快照：明确报错（同 006 口径）
- MCP server 启动时外部服务（gptr-mcp/嵌入）不在线：server 正常启动，
  工具调用时才按各自口径报错或降级，不做启动期硬检查

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 以 FastMCP 提供 MCP server，暴露六个工具：
  research_asset / create_world / run_simulation / export_events /
  web_search / web_fetch，均带参数 schema
- **FR-002**: 工具 MUST 只做协议封装（参数适配 + 结果序列化），
  业务逻辑 MUST 全部复用 orchestrator 既有模块，MUST NOT 复制业务代码
- **FR-003**: 传输方式与监听地址 MUST 可经环境变量配置
  （默认 streamable-http 本机地址）；server 启动 MUST NOT 依赖任何
  外部服务在线
- **FR-004**: 工具失败 MUST 返回结构化可读错误（错误类型 + 原因），
  MUST NOT 使 server 进程崩溃或泄漏堆栈给客户端
- **FR-005**: run_simulation MUST 支持后端选择与 resume 参数；
  真后端为默认，mock 后端供测试与演示
- **FR-006**: 本特性 MUST NOT 改动资产/事件契约与 orchestrator 既有行为；
  M1、M2、003、004、005、006 既有验收 MUST 不回归
- **FR-007**: 离线测试 MUST 覆盖全部六个工具（进程内客户端 + 既有 mock
  基线），不依赖任何外部进程与真实 API

### Key Entities *(include if feature involves data)*

- **工具调用链标识**：asset_id → world_id → run_id → 导出路径 ——
  各工具返回值中的衔接字段，客户端据此串联流程
- **工具错误**：错误类型 + 可读原因 —— 客户端排障的唯一依据

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 离线环境以进程内 MCP 客户端完成
  research_asset → create_world → run_simulation(mock 后端) → export_events
  全链，产出与 CLI 形态一致（事件契约 100% 通过）
- **SC-002**: 六个工具全部可被发现且带 schema；三类错误场景
  （坏参数/缺前置/服务不可达）返回结构化可读错误，server 存活率 100%
- **SC-003**: M1-M6 离线回归 100% 通过
- **SC-004**: server 代码中零业务逻辑复制（grep 可证：只 import orchestrator
  既有模块与插件包）

## Assumptions

- MCP 客户端为支持 streamable-http 的 LLM 客户端；stdio 传输经
  `MCP_TRANSPORT=stdio` 可用（converge T011 追认：fastmcp 原生支持、零额外成本，
  适配桌面类 MCP 客户端），其客户端配置由用户自理
- 真后端 run_simulation 为同步长调用，超时口径在 plan 阶段定
  （候选：按 ticks 线性计算 + 客户端可覆盖）
- FastMCP 版本与 005 gptr-mcp 服务端验证过的兼容（fastmcp-slim[server] 教训
  已记录，主项目装哪个形态 plan 阶段定）
- 本特性不做：MCP 鉴权/多用户、工具调用的进度推送
  （长轮询/SSE 进度）、DM 裁判工具的暴露
