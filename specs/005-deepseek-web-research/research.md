# Phase 0 Research: GPT-Researcher 接入 DeepSeek 检索腿（B 方案）

日期：2026-10-20。retriever 扩展点事实来自 fork 源码调查（子代理），
DeepSeek API 事实来自官方文档（api-docs.deepseek.com/zh-cn/guides/search/）。

## R1: 接入形态 — entry-point 插件包（fork 零改动）

**Decision**: 在本仓库新建插件包 `plugins/gptr-deepseek-retriever/`，
经 entry-point 组 `gpt_researcher.retrievers` 注册名为 `deepseek` 的 retriever，
安装进 gptr-mcp venv 后 `RETRIEVER=deepseek` 生效。
包内分两层：`client.py` 提供 `web_search()` / `web_fetch()` 两个独立工具函数
（HTTP + 重试 + 容错的唯一实现，FR-009），`deepseek.py` 的 retriever 类
复用它们做字段映射。主项目经 path 依赖引入该包，两个工具函数对
orchestrator / 未来 M5 MCP server 直接可调。

**机制证据**（fork 源码）:
- `retrievers/utils.py:86-120`：retriever 白名单 = retrievers/ 子目录扫描
  + entry-point 插件名，`RETRIEVER` 校验自动通过
- `actions/retriever.py:135-147`：`get_retriever` 的 match/case 未命中时落到
  `_load_plugin_retriever`，查 entry-point 组并 load
- 鸭子类型契约（无强制基类）：构造 `(query, headers=None, query_domains=None)`，
  `search(max_results=...)` **必须同步**（调用方 asyncio.to_thread 包装），
  返回 `list[dict]` 至少含 `href` 或 `url`
- 配置惯例：`__init__` 直接读环境变量（tavily/searx 同款）

**Alternatives considered**: 直接改 fork（~70 行、2 个文件 + 新目录）——
代码落到仓库外、不可测试不可版本化，否决；`RETRIEVER=custom` + 转换代理——
多一层常驻进程，否决。

## R2: 字段映射 — content 全文直通（省掉抓取轮）

**Decision**: 类级声明 `requires_scraping = False`，逐条映射：
`url → href`，`content or summary → raw_content`（content 为空用 summary 垫底，
两者皆空丢弃该条）。Search 请求恒带 `need_content=true`。

**机制证据**:
- `skills/researcher.py:903-915`：`requires_scraping=False` 时 raw_content
  直接计入 research_sources 与 visited_urls，**不再发起网页抓取**
- 必须显式声明：不声明会落入遗留启发式（`len(raw_content)>100` 才算全文，
  researcher.py:916-924）——fork 给 searx snippet 截断躲的就是这个坑
- 规划阶段读 `body`（deep_research.py:300-333）：同时映射 `summary or snippet
  → body`，保证子查询规划质量
- `rerank_score`/`date`/`authority` 下游不读，丢弃

**Fetch 补抓**：正文与摘要皆缺的条目若排序靠前（rerank_score ≥ 1.5），
插件自行调 Fetch 补抓，上限 `DEEPSEEK_FETCH_MAX`（默认 2，成本闸门）；
补抓失败回退摘要/丢弃。

## R3: 容错语义（FR-004，GPT-R 无兜底路径的约束）

**Decision**: 插件任何路径不抛异常：
- `__init__` 缺 `DEEPSEEK_API_KEY`：print 警告，`search()` 返回 `[]`
- `search()` 内：429/5xx 短退避重试 ≤ `DEEPSEEK_SEARCH_RETRIES`（默认 2 次，
  退避 2s/4s）；401/402 打印原因；其它异常一并捕获 → 返回 `[]`
- 响应做 dict/逐条校验（tavily 模板 137-147 行同款），API 返回异常类型不炸
- requests/httpx 调用必须带 timeout（30s），否则线程池挂死

**机制证据**: `get_search_results`（actions/query_processing.py:73-81，
初始搜索与规划都走）**没有 try**，插件抛出会炸掉整个调研；
单 retriever 全空时 writer 有"无法生成报告"防护（skills/writer.py:79-88），
004 管线另有"无来源拒绝"口径，空结果语义闭环。

## R4: 服务端配置切换（FR-007）

gptr-mcp 启动环境变化（仓库外，quickstart 文档化）：
- 新增：`RETRIEVER=deepseek`；venv 内 `pip install <本仓库插件包路径>`
- 保留：`SEARX_URL`（searx 腿切回即用）；`RETRIEVER` 支持逗号分隔多腿
  （config.py:79,189-202），本特性只用单腿
- 插件未安装却设 `RETRIEVER=deepseek`：校验阶段即报 unknown retriever
  （US2-AC2 的可诊断失败信号）

**溯源标识**：004 管线的 `provenance.retriever` 对 gptr-mcp 路径由
`GPTR_MCP_RETRIEVER_LABEL` 环境变量给出，默认改为 `gptr-mcp(deepseek-search)`
（客户端无法从响应反推服务端检索腿，故显式配置；004 的 searx 默认值随之过时，
research.py 仅改默认值与读取逻辑，行为兼容）。

## R5: 成本口径

- GPT-R 标准调研（research_report）≈ 5 次 Search/调研（1 初始 + ~4 子查询，
  MAX_ITERATIONS=3 + 原查询），+ ≤2 次 Fetch 补抓
- 按 5 元/千次计，单次调研检索成本 ≈ 0.025-0.035 元，可忽略但记账可知
- deep_research 递归模式量级高一个数量级，本特性不启用

## R6: 环境变量清单

**插件（gptr-mcp 服务端 venv 进程读取）**:

| 变量 | 含义 | 默认 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 密钥（复用） | 无（缺失=警告+空结果） |
| `DEEPSEEK_SEARCH_BASE_URL` | 端点 base | `https://api.deepseek.com` |
| `DEEPSEEK_FETCH_MAX` | Fetch 补抓上限/次检索 | `2` |
| `DEEPSEEK_SEARCH_RETRIES` | 429/5xx 重试上限 | `2` |

**本项目（客户端）**: `GPTR_MCP_RETRIEVER_LABEL`（溯源标识，
默认 `gptr-mcp(deepseek-search)`）。

## R7: 测试策略（FR-008，离线 Mock 基线）

插件包在本仓库，测试直接 import 插件类、mock HTTP 层：
- 字段映射：content→raw_content、summary 垫底、皆空丢弃、body 映射
- `requires_scraping is False` 显式声明
- 429→重试→成功；429 持续→返回 []；401/402→[]+警告；响应非 dict→[]
- 补抓：皆空条目触发 Fetch（按 rerank_score 优先级、上限约束）、失败回退
- query 截断 128；缺 key → [] 不抛
- 004 既有 17 项测试保持绿（FR-008）

## R8: 依赖与回归面

- 插件包依赖仅 httpx（主项目经 uv path 依赖引入，gptr-mcp venv 装插件时一并解析）
- fork 零改动；gptr-mcp server.py 零改动；004 管线仅 retriever 标签默认值
  与 env 读取一处小改
- M1/M2/003/004 回归兜底；T017（全链路同义去重复验）随 SC-002 一并关闭
