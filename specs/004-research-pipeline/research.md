# Phase 0 Research: 自动资产调研管线

日期：2026-10-20（R2/R3/R6-R8 经用户指示修订：调研编排改接 GPT-Researcher MCP）。
组件调研基于本地副本源码（SearXNGforWindows / gpt-researcher 0.16.0-fork /
gptr-mcp@main，证据见各节）。

## R1: 检索层 — SearXNG（本地 Windows 发行版），作为 GPT-Researcher 的检索后端

**Decision**: 以 `D:\kimicode_repos\my-gpt-research\SearXNGforWindows` 为检索服务
（仓库外，用户按需启动）。本项目不直接调用它 —— 它配置为 GPT-Researcher MCP
服务端的 `RETRIEVER=searx` + `SEARX_URL`（服务端环境变量）。

**关键事实**:
- 启动：仓库根目录跑 `searx/webapp.py`，默认 `127.0.0.1:8888`；**CWD 敏感**
- JSON API 默认已开启（`formats: [html, json]`），满足 gpt-researcher searx
  retriever 的硬要求（`searx.py:68-89`，`response.json()`）
- 默认仅 360search 引擎启用（其余被 disable，反爬原因），用户可自行加开
- AGPL-3.0：只作网络服务调用、不分发，记录于文档

## R2: 编排层 — 接 GPT-Researcher MCP 服务（gptr-mcp），进程外隔离

**Decision**（用户拍板）: 调研编排走 GPT-Researcher 的官方 MCP 服务
`gptr-mcp`（已 clone 至 `D:\kimicode_repos\my-gpt-research\gptr-mcp`）。
它作为**仓库外的独立进程**运行（独立 venv），本项目只做 MCP 客户端。
140+ 依赖因此全部隔离在本项目 uv lock 之外，R2 初版"自研薄管线"作废。

**gptr-mcp server.py 核实事实**:
- FastMCP 封装 `GPTResearcher`；`deep_research(query)` 一个 tool 即返回
  `{research_id, context, sources, source_urls}`（server.py:93-137）——
  context 供我们结构化抽取，source_urls 直接填契约溯源，**无需自抓网页**
- 另有 `quick_search` / `write_report` / `get_research_sources` /
  `get_research_context`；`GET /health` 健康检查（server.py:273）
- transport：`MCP_TRANSPORT=streamable-http`（或 sse），绑 `0.0.0.0:8000`
  （server.py:285-306）
- **坑**：`run_server()` 启动前硬性检查 `OPENAI_API_KEY`（server.py:280-282），
  用 DeepSeek 时须把 OPENAI_API_KEY 也设上（值同 DEEPSEEK_API_KEY）
- 配置走环境变量（gpt-researcher Config env 优先）：`RETRIEVER=searx`、
  `SEARX_URL`、`FAST_LLM/SMART_LLM/STRATEGIC_LLM=deepseek:deepseek-chat`、
  `DEEPSEEK_API_KEY`；**必须**把 `SMART_TOKEN_LIMIT`/`STRATEGIC_TOKEN_LIMIT`
  压到 ≤8000（默认 12000 超 deepseek-chat 输出上限）
- 服务端 venv 的 gpt-researcher 从**本地 fork 路径安装**（保留 searx 截断、
  keyword context filter 等补丁，避免默认走 embeddings）

**成本口径**：一次 deep_research ≈ 3-5 次 LLM 调用 + 数次检索 + 最多 ~20 页
抓取（fork 默认 MAX_ITERATIONS=3、每查询 5 结果）。用户已接受该成本换编排能力。

**Alternatives considered**: 自研薄管线（初版 R2）——被用户指示替换；
进程内 import gpt-researcher——依赖进 lock，否；gptr-mcp stdio 模式——
与"外部常驻服务 + 环境变量寻址"的项目形态不符，选 HTTP transport。

## R3: 深抓层 — 不需要（GPT-Researcher 服务端自抓）

**Decision**: 本项目不装 crawl4ai。deep_research 的 context 已由服务端
经检索 + BeautifulSoup 抓取 + 上下文压缩产出，客户端拿到的就是可用材料。
初版 R3（crawl4ai 深抓）作废。

**Alternatives considered**: crawl4ai（重依赖 playwright，且与 GPT-R 抓取
角色重叠）；若未来证明 GPT-R 抓取质量不足，再单独特性评估客户端补强。

## R4: 结构化抽取 — 复用 llm.chat_json() + 契约校验单一入口

**Decision**: 同初版。deep_research 返回的 context + 类型指引进 `chat_json`
（json_object 模式，002 已验证 DeepSeek 兼容）产出草稿，
`store.put_asset()` 的 schema 校验把关（原则 III 单一入口）。
JSON 漂移/缺字段 → 重试 1 次 → 仍失败干净报错，零写入（FR-003）。

**契约事实**（schemas/asset.schema.json）:
- 必填：`asset_id`/`type`/`name`/`provenance`（含 `researched_at`/`retriever`/
  `model`/`confidence` 0-1）
- character 另需 `appearance.visual_prompt` + `persona_spec` 五字段
- 来源 URL 放 `historical_context.sources`（数组）
- `asset_id` 模式 `^(char|prop|scene|epoch)_[a-z0-9_]+$`

## R5: 语义去重 — 共享嵌入助手抽到 orchestrator/embedding.py（同初版）

**Decision**: 003 的 `_embedding_config` / `_build_embedding_model`（及常量）
提升到新模块 `orchestrator/embedding.py`，persona 适配器改为 import
（行为不变，回归套件兜底）。去重算法：
- 文本 = `name + appearance.description/visual_prompt`，同一 type 内比较
- 余弦 ≥ `RESEARCH_DEDUP_THRESHOLD`（默认 0.85）→ 判重，返回已有 asset_id
- 嵌入不可用 → name 精确匹配 + 降级日志（FR-005，与 003 语义一致）
- store.py 加只读 `list_assets(type)`；现算向量，不做缓存

## R6: 环境变量清单（FR-007，原则 VI）

**本项目（客户端）**:

| 变量 | 含义 | 默认 |
|---|---|---|
| `GPTR_MCP_URL` | gptr-mcp 服务端点 | 无（未设=明确报错，FR-007） |
| `RESEARCH_TIMEOUT_S` | MCP 调用超时 | `180`（deep_research 是长调用） |
| `RESEARCH_DEDUP_THRESHOLD` | 语义去重余弦阈值 | `0.85` |

复用：`EMBEDDING_*`（003）、`DEEPSEEK_*`/`OPENAI_*`（002）。

**gptr-mcp 服务端**（仓库外，文档记录）: `MCP_TRANSPORT=streamable-http`、
`RETRIEVER=searx`、`SEARX_URL`、`FAST_LLM/SMART_LLM/STRATEGIC_LLM`、
`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`（启动硬检查）、
`SMART_TOKEN_LIMIT=8000`、`STRATEGIC_TOKEN_LIMIT=8000`；
SearXNG 服务端另需启动。键位进 `.env.example`（客户端部分）；
gptr-mcp 服务与 SearXNG 在仓库外。

## R7: 模块布局与入口（原则 II/IV）

- `orchestrator/research.py`：调研管线 + MCP 客户端封装 —— GPT-Researcher 栈的
  全部接触面集中于此一个适配器模块（list_tools/call_tool 接缝可 mock）
- `orchestrator/embedding.py`：R5 共享嵌入助手（003 代码搬家）
- `scripts/research_asset.py`：CLI 入口（`--query --type --db`）
- 离线测试：mock MCP call_tool / llm / 嵌入三层，不依赖任何外部进程
- `store.py`：仅加 `list_assets(type)` 读方法
- 新增依赖仅 `mcp`（官方 MCP 客户端包，uv add + pin，原则 V）

## R8: asset_id 生成与溯源填充

- `asset_id` = `{prefix}_{sha1(name)[:10]}`（确定性可重入）
- `provenance.retriever = "gptr-mcp(searxng)"`（接 MCP 后的真实调研链；
  手册的 "searxng+crawl4ai" 口径随技术路线修订）
- `provenance.model` = 抽取用模型名；`researched_at` = ISO8601；
  `confidence` = `min(0.5 + 0.1 × 成功来源数, 0.9)`
- `historical_context.sources` = deep_research 返回的 source_urls（非空才入库）

## R9: 依赖与回归面

- 本项目新增依赖仅 `mcp` 客户端包；gpt-researcher/fastmcp 等 140+ 依赖
  全部隔离在 gptr-mcp 服务端 venv（仓库外）
- 003 代码搬家（R5）是唯一触碰既有特性的改动，46 项离线回归兜底
- M1/M2/003 不回归；调研管线与仿真链路无共享运行时状态（FR-006）

## 风险备忘

- **gptr-mcp 服务端 venv 搭建**：requirements 钉 `gpt-researcher>=0.14.0`，
  需改为本地 fork 路径安装（保留补丁）；tasks 首个任务为服务端搭建冒烟
  spike（venv + 启动 + /health + 最小 deep_research 调通）
- **streamable-http vs sse**：优先 streamable-http（FastMCP 2.x 推荐），
  spike 失败则退 sse（端点 /sse）
- **360search 单引擎覆盖**：真机验收检索质量差时用户在 SearXNG settings.yml
  加开引擎，不动本仓库代码
- **deep_research token 成本**：每次 3-5 次 LLM 调用，用户已知情接受
