# Feature Specification: DeepSeek Web 调研后端（与 gptr-mcp 并存）

**Feature Branch**: `005-deepseek-web-research`

**Created**: 2026-10-20

**Status**: Draft

**Input**: User description: "用 DeepSeek Web Search 和 Web Fetch 实现一个适配本项目的
Research 后端，与 004 已实现的 gptr-mcp 调研管线并存：复用同一 research_asset 管线
（抽取/去重/入库不变），后端经环境变量选择；DeepSeek 后端无需外部常驻服务；
计费按次需有成本意识；故障语义清晰；离线 Mock 基线可测；M1-M4 不回归。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - DeepSeek 后端完成调研入库 (Priority: P1)

不启动任何外部服务（不要 SearXNG、不要 gptr-mcp），只凭 DeepSeek 账号，
给查询词就能完成"检索 → 抓取 → 结构化 → 契约资产入库"全流程，
资产形态与 004 产出完全一致。

**Why this priority**: 这是本特性的全部价值 —— 004 后端依赖两个常驻进程且
被 360search 限流卡过；DeepSeek 官方 Search/Fetch 是零运维的替代检索腿。

**Independent Test**: 不启动任何外部服务，用真实查询词跑 CLI，
确认资产入库、契约通过、溯源标识为 DeepSeek 调研链。

**Acceptance Scenarios**:

1. **Given** 仅配置 DeepSeek 密钥且选择 DeepSeek 后端，**When** 用人物/场景
   查询词运行调研管线，**Then** 契约校验通过的资产入库，来源列表非空，
   溯源字段记录 DeepSeek 检索链
2. **Given** 检索有结果但正文缺失，**When** 管线抓取重点 URL 补全文，
   **Then** 结构化材料充足可抽取；全部正文不可得时明确失败而非编造入库

---

### User Story 2 - 双后端并存可切换 (Priority: P2)

同一套管线代码，改一个环境变量就能在 DeepSeek 后端与 004 的 gptr-mcp
后端之间切换；两个后端产出的资产契约形态一致，互不影响。

**Why this priority**: 并存是本特性的明确约束 —— 004 后端是已验收资产，
不能为引入新后端而破坏；切换能力让两条检索腿互为备份（一条被限流换另一条）。

**Independent Test**: 同一 CLI，分别用两个后端各跑一次调研，
确认产出契约形态一致；004 既有离线测试全部保持绿。

**Acceptance Scenarios**:

1. **Given** 两个后端均可用，**When** 分别选择两个后端运行同一查询，
   **Then** 均产出契约资产，溯源字段各自记录真实调研链
2. **Given** 未显式选择后端，**When** 运行调研管线，
   **Then** 按文档化的默认后端执行，行为可预期

---

### User Story 3 - 成本与故障语义清晰 (Priority: P3)

Search/Fetch 按次计费，管线对调用次数有上限；限流（429）与超时退避重试，
余额不足（402）明确报错不重试；检索无结果时明确失败且不产生入库。

**Why this priority**: 计费 API 的失控重试就是烧钱；清晰的故障语义是
US1/US2 能长期可靠运行的前提。

**Independent Test**: 离线 mock 429/402/无结果三类场景，验证重试、
报错与零写入行为；真机跑一次"无结果查询"确认明确失败。

**Acceptance Scenarios**:

1. **Given** Search 返回 429/408/5xx，**When** 管线重试，
   **Then** 按退避策略重试至上限后明确报错，零写入
2. **Given** 账号余额不足（402），**When** 运行管线，
   **Then** 立即明确报出余额问题，不做无谓重试
3. **Given** 查询无任何检索结果，**When** 运行管线，
   **Then** 明确报"无来源"失败，零写入（该情形官方不计费）

---

### Edge Cases

- 检索结果全部正文缺失且 Fetch 补抓失败：明确失败，不用空材料编造入库
- 查询词超长（>128 字符）：截断或拒绝（设计时定口径），不发起无效计费调用
- Fetch 目标站点拒绝（403/404）：跳过该源继续，全部失败才报错
- 与 004 相同的空查询、抽取漂移、契约校验失败：沿用既有语义（拒绝/重试）

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 实现基于 DeepSeek Search/Fetch 的调研检索层，
  产出与 004 检索层相同形态的材料（上下文文本 + 来源列表 + 来源 URL），
  供同一管线的抽取/去重/入库复用
- **FR-002**: 后端选择 MUST 经环境变量读取，支持 DeepSeek 与 gptr-mcp 两个后端；
  未设置时按文档化默认值执行；两后端 MUST NOT 互相影响对方行为
- **FR-003**: Search/Fetch 端点 MUST 由既有 DeepSeek 基础地址派生、
  密钥复用既有 DeepSeek 密钥变量，MUST NOT 新增硬编码地址或重复密钥配置
- **FR-004**: 429/408/5xx MUST 退避重试（有上限）；402 MUST 明确报余额不足且
  不重试；其它 4xx MUST NOT 原样重试（与官方错误语义一致）
- **FR-005**: 单次调研的 Search 与 Fetch 调用次数 MUST 有可配置上限
  （成本闸门），达到上限即停止并用已有材料继续或明确失败
- **FR-006**: 检索无结果或材料不足时 MUST 明确失败、零写入，MUST NOT 用
  空材料编造资产入库
- **FR-007**: DeepSeek 检索接入代码 MUST 集中在调研适配器模块内（宪章原则 II），
  离线测试 MUST 能以 Mock 基线覆盖，不依赖任何真实 API
- **FR-008**: 本特性 MUST NOT 改动资产/事件契约与 004 的 gptr-mcp 后端代码路径；
  M1、M2、003、004 既有验收 MUST 不回归

### Key Entities *(include if feature involves data)*

- **检索结果条目**：标题、URL、短摘要、长摘要、正文（可空）、排序分、
  权威性 —— 运行时材料，URL 随资产溯源持久化
- **抓取页面**：标题、Markdown 正文 —— 运行时材料，正文缺失源的补抓手段
- **调研后端标识**：DeepSeek / gptr-mcp —— 环境变量来源，
  溯源字段据此记录真实调研链

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 零外部常驻服务条件下，用 DeepSeek 后端各跑一个人物类与场景类
  真实查询词，各产出一份契约校验通过的入库资产，来源列表均 ≥ 1 条
- **SC-002**: 两个后端分别跑通同一 CLI，产出契约形态一致；
  004 既有离线测试 100% 保持绿
- **SC-003**: 离线 mock 覆盖 429 退避 / 402 报余额 / 无结果三类场景，
  行为 100% 符合 FR-004/FR-006
- **SC-004**: M1 / M2 / 003 / 004 离线回归 100% 通过
- **SC-005**: 检索接入代码 100% 位于调研适配器模块内，仓库无新增硬编码地址

## Assumptions

- DeepSeek Search/Fetch 为官方 JSON API（`POST {base}/v1/tools/search`、
  `/v1/tools/fetch`，Bearer 鉴权），2026-11-01 起按次计费（5 元/千次成功请求，
  失败/无结果不计费）；真机验收会产生少量调用费用，属预期
- Search 的 `summary`（600-800 字符）与 `need_content` 正文通常足以支撑
  结构化抽取；Fetch 用于正文缺失的重点源补抓，调用次数受 FR-005 上限约束
- DeepSeek 裸 API 无子查询编排能力；是否需要"先规划子查询再检索"由 plan
  阶段评估，本规格不锁定（单查询检索为基线）
- 默认后端口径在 plan 阶段确定并文档化（候选：DeepSeek 优先，gptr-mcp 备份）
- 本特性不做：后端自动故障转移（一条失败自动换另一条）、检索结果缓存、
  批量调研
