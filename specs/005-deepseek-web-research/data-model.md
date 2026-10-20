# Data Model: GPT-Researcher 接入 DeepSeek 检索腿

本特性不改资产/事件契约（FR-008），不引入持久化实体。
以下为运行时概念模型与跨层映射口径。

## DeepSeek 检索结果条目（SearchResult，插件输入）

| 字段 | 类型 | 插件消费方式 |
|---|---|---|
| url | str | → `href`；Fetch 目标；溯源 URL |
| title | str | → `title`（记录用） |
| content | str | 正文（`need_content=true` 时可空）→ 优先 `raw_content` |
| summary | str | 长摘要 → content 缺失时 `raw_content` 垫底；→ `body`（规划用）首选 |
| snippet | str | 短摘要 → `body` 次选 |
| rerank_score | number | ≥1.5 且正文摘要皆缺 → Fetch 补抓候选（按分数降序） |
| date / authority / site_* | - | 丢弃（下游不读） |

## 工具函数契约（FR-009，仓库内唯一实现）

- `web_search(query, count=8, need_content=True) -> list[dict]`：
  成功返回 SearchResult 条目列表（见上节）；无结果返回 []；
  429/5xx 退避重试至上限后返回 []；401/402 打印原因返回 []；不抛异常
- `web_fetch(url) -> dict | None`：成功返回 `{title, content}`；
  403/404/超时返回 None（调用方跳源）；不抛异常

## GPT-R retriever 条目（插件输出，鸭子类型契约）

| 键 | 内容 | 规则 |
|---|---|---|
| href | 条目 URL | 必有，否则该条丢弃 |
| raw_content | content 或 summary 或 Fetch 正文 | requires_scraping=False 的全文位 |
| body | summary 或 snippet | 规划阶段阅读位 |
| title | 标题 | 记录用 |

类级声明 `requires_scraping = False`（显式，防遗留启发式误判）。

## Fetch 补抓（成本闸门内）

- 触发：content 与 summary 皆空 且 rerank_score ≥ 1.5
- 上限：`DEEPSEEK_FETCH_MAX`（默认 2）/次 search() 调用
- 失败（403/404/超时）：回退摘要；摘要也无 → 丢弃该条

## 环境变量（无持久化）

插件侧（gptr-mcp venv 进程）：`DEEPSEEK_API_KEY`（复用）、
`DEEPSEEK_SEARCH_BASE_URL`（默认官方地址）、`DEEPSEEK_FETCH_MAX`（2）、
`DEEPSEEK_SEARCH_RETRIES`（2）。

客户端侧（本项目）：`GPTR_MCP_RETRIEVER_LABEL`
（默认 `gptr-mcp(deepseek-search)`，填 `provenance.retriever`）。

## 查询词约束

- search() 入口截断到 128 Unicode 字符（官方上限），GPT-R 子查询
  可能含操作符，原样透传不清洗（官方支持搜索语法）
- 空查询：GPT-R 不产生空调用；若发生，插件直接返回 []
