# Feature Specification: GPT-Researcher 接入 DeepSeek 检索腿

**Feature Branch**: `005-deepseek-web-research`

**Created**: 2026-10-20

**Status**: Draft（B 方案修订版，替代同日 A 方案初稿）

**Input**: User description: "用 GPT-Researcher 接入 DeepSeek 的 Search API：
为 gpt-researcher 新增 DeepSeek 检索 retriever（entry-point 插件形态，代码在本仓库，
fork 零改动），gptr-mcp 的 RETRIEVER 切换为 deepseek，替换被限流的 360search 检索腿；
DeepSeek Search 的 content 全文直接作为调研材料（省去抓取轮）；计费与故障语义清晰；
离线 Mock 基线可测；M1-M4 不回归。（经方案比选拍板 B：保留 GPT-R 编排，
DeepSeek Search 作检索腿；A 方案'仓库内直连后端'作废。）"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - DeepSeek 检索腿跑通调研入库 (Priority: P1)

不启动 SearXNG，gptr-mcp 的检索后端换成 DeepSeek Search 后，
"查询词 → deep_research → 结构化 → 契约资产入库"全流程照常工作，
且不再受 360search 反爬限流影响。

**Why this priority**: 这是本特性的全部价值 —— 004 的检索腿（360search）
已被实测限流卡死（T017 挂起）；DeepSeek 官方 Search 是稳定替代，
其 content 字段自带正文，还能省掉 GPT-R 的整轮网页抓取。

**Independent Test**: SearXNG 停止、gptr-mcp 以 DeepSeek 检索腿运行，
用真实查询词跑 CLI，确认资产入库、契约通过、来源非空。

**Acceptance Scenarios**:

1. **Given** gptr-mcp 配置 DeepSeek 检索腿、SearXNG 未启动，
   **When** 用人物/场景查询词运行调研管线，
   **Then** 契约校验通过的资产入库，来源列表非空，
   溯源字段记录 DeepSeek 检索链
2. **Given** DeepSeek Search 返回的条目自带正文，**When** GPT-R 消费检索结果，
   **Then** 正文直接作为调研材料，不再对同源发起重复网页抓取

---

### User Story 2 - 检索腿可切换、插件可回归 (Priority: P2)

检索腿是服务端环境变量的一次切换：DeepSeek 腿与 004 的 searx 腿并存，
按需换回；插件代码在本仓库内，离线测试可独立验证其行为。

**Why this priority**: 检索腿是外部依赖最脆弱的一环（已被限流实证），
可切换意味着任何一条腿出问题都有退路；插件入仓库是宪章
（可测试、可评审、版本化）的必然要求。

**Independent Test**: 离线 mock 验证插件字段映射与容错；
以 searx 腿启动 gptr-mcp 确认 004 路径仍可工作（与服务端配置一致）。

**Acceptance Scenarios**:

1. **Given** gptr-mcp venv 已安装插件，**When** RETRIEVER 分别设为
   deepseek 与 searx 启动服务，**Then** 两种配置下服务均正常接受调研请求，
   溯源标识与真实检索链一致
2. **Given** 插件未安装却设 RETRIEVER=deepseek，**When** 发起调研，
   **Then** 服务端给出可诊断的失败信号（不会静默退回其它引擎）

---

### User Story 3 - 计费与故障语义清晰 (Priority: P3)

Search/Fetch 按次计费，插件对补抓次数有上限；限流（429）退避重试有上限；
任何检索异常不得让调研进程崩溃，材料为空时按既有"无来源拒绝"口径失败。

**Why this priority**: 检索异常被 GPT-R 内部放大（初始搜索路径无异常兜底），
插件必须自己兜住；计费 API 的失控重试就是烧钱。

**Independent Test**: 离线 mock 429/402/无结果/正文缺失四类场景，
验证插件的重试、容错与降级行为。

**Acceptance Scenarios**:

1. **Given** Search 返回 429/5xx，**When** 插件重试，
   **Then** 短退避重试至上限后返回空结果（由管线按无来源拒绝），不抛异常
2. **Given** 条目正文缺失，**When** 插件补抓，
   **Then** 仅对高优先级条目共 ≤ 上限次 Fetch，失败回退摘要，
   不产生无限补抓
3. **Given** 密钥缺失或余额不足（401/402），**When** 发起检索，
   **Then** 返回空结果并打印可诊断原因，调研按无来源明确失败

---

### Edge Cases

- 检索结果全部无正文且补抓全失败：回退摘要作为材料；摘要也为空则该源丢弃
- LLM 生成的子查询含搜索操作符或超长：截断到官方上限（128 字符）再发请求
- GPT-R 并发调用插件：插件无内部可变状态，天然并发安全
- 与 004 相同的空查询、抽取漂移、契约校验失败：沿用既有语义

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 提供 DeepSeek Search 的 GPT-Researcher retriever 插件，
  符合其 retriever 鸭子类型契约（同步 search(max_results)、
  返回含 href 的条目列表、显式声明 requires_scraping）
- **FR-002**: 插件代码 MUST 位于本仓库（entry-point 插件包形态，
  gpt-researcher fork 零改动），安装进 gptr-mcp 服务端 venv 后
  RETRIEVER=deepseek 可用
- **FR-003**: Search 返回的正文（content）MUST 直接映射为调研材料
  （raw_content + requires_scraping=False），避免对同源的重复抓取；
  正文缺失时 MUST 以摘要垫底，并可经 Fetch 补抓（次数有上限）
- **FR-004**: 插件 MUST 不在构造或检索中抛异常：429/5xx 短退避重试至上限、
  401/402 打印原因，均以返回空结果收尾（配合 GPT-R 无兜底路径）
- **FR-005**: Search/Fetch 端点与密钥 MUST 从环境变量读取
  （密钥复用既有 DeepSeek 密钥变量），MUST NOT 硬编码密钥；
  官方默认地址仅作可覆盖的默认值
- **FR-006**: 单次检索的 query MUST 截断到官方上限（128 字符）；
  单次调研的 Fetch 补抓次数 MUST 有可配置上限（成本闸门）
- **FR-007**: gptr-mcp 检索腿切换 MUST 只是服务端环境变量变化
  （RETRIEVER=deepseek），searx 腿保留可切回；
  资产溯源 MUST 记录真实检索链标识
- **FR-008**: 插件 MUST 有可离线运行的 Mock 基线测试（不依赖任何真实 API）；
  本特性 MUST NOT 改动资产/事件契约与 004 管线代码路径；
  M1、M2、003、004 既有验收 MUST 不回归
- **FR-009**: DeepSeek Search 与 Fetch MUST 以两个可独立调用的工具函数形态
  提供（含统一的重试/容错语义的唯一实现），retriever 插件 MUST 复用该实现
  而非另写一套；工具函数对本仓库其它代码（及未来 MCP 工具封装）可直接调用

### Key Entities *(include if feature involves data)*

- **检索结果条目**：标题、URL、摘要、正文（可空）、排序分 —— 运行时材料，
  经插件映射为 GPT-R 的 href/raw_content 形态
- **补抓页面**：标题、Markdown 正文 —— 正文缺失源的补救手段，次数受闸门约束
- **检索腿标识**：deepseek / searx —— 服务端环境变量来源，
  资产溯源据此记录真实检索链

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: SearXNG 停止、gptr-mcp 以 DeepSeek 检索腿运行时，各用一个人物类
  与场景类真实查询词，各产出一份契约校验通过的入库资产，来源列表均 ≥ 1 条
- **SC-002**: 用 DeepSeek 检索腿对同一主题做全链路重复调研（经 gptr-mcp），
  语义去重生效、库中对应资产数量为 1（一并关闭 004 遗留 T017）
- **SC-003**: 插件与工具函数离线测试覆盖字段映射 / 429 重试 / 无结果 /
  正文缺失补抓四类场景，100% 通过；004 既有离线测试 100% 保持绿
- **SC-004**: M1 / M2 / 003 / 004 离线回归 100% 通过
- **SC-005**: 插件代码 100% 位于本仓库插件包内，gpt-researcher fork 零改动，
  仓库无硬编码密钥

## Assumptions

- DeepSeek Search/Fetch 为官方 JSON API（`POST {base}/v1/tools/search|fetch`，
  Bearer 鉴权），按次计费（5 元/千次成功请求，失败/无结果不计费）；
  真机验收会产生少量调用费用，属预期
- GPT-R 标准调研（research_report）单次约 5 次 Search 调用
  （1 初始 + ~4 子查询），成本可预期；deep_research 模式量级更高，本特性不启用
- GPT-R 的 retriever entry-point 插件机制（`gpt_researcher.retrievers` 组）
  经源码核实可用（retrievers/utils.py 与 actions/retriever.py）
- 插件运行环境是 gptr-mcp 服务端 venv（gpt-researcher 本地 fork 已装）；
  插件与 fork 的兼容面以鸭子类型契约为准，fork 升级时需复核
- 工具函数的 MCP 协议封装属 M5 范围，本特性只交付可调用的函数形态
- 本特性不做：DeepSeek 直连仓库的轻量后端（A 方案，已作废）、
  searx 腿移除、检索结果缓存
