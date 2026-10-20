# Data Model: DeepSeek Web 调研后端

本特性不改资产/事件契约（FR-008），不引入持久化实体。
以下为运行时概念模型（字段对齐官方 API 文档）。

## 检索结果条目（SearchResult，运行时）

| 字段 | 类型 | 用途 |
|---|---|---|
| title | str | context 拼接、sources 记录 |
| url | str | source_urls、Fetch 目标、溯源持久化 |
| content | str | 正文（`need_content=true` 时可能有，空串表示缺失） |
| summary | str | 长摘要（600-800 字符），content 缺失时垫底 |
| snippet | str | 短摘要，不用于抽取（展示级） |
| rerank_score | number | 排序分（≥1.5 优质），Fetch 补抓优先级依据 |
| authority | int | 权威性 0-4，记录不用 |
| date / site_name | str\|null | 记录不用 |

## 抓取页面（FetchedPage，运行时）

| 字段 | 类型 | 用途 |
|---|---|---|
| title | str | context 拼接 |
| content | str | Markdown 正文，补抓材料 |

## 组装后的检索层产出（DeepResearchShape，跨后端统一）

| 字段 | 来源 | 说明 |
|---|---|---|
| status | 固定 `"success"` | 失败走 ResearchError 异常，不进 dict |
| context | 条目「标题+URL+正文/摘要」拼接 | 抽取材料 |
| sources | `[{url, title}]` | 溯源明细 |
| source_urls | 全部条目 URL | 契约 sources 填充；空 → 无来源拒绝 |
| retriever | 固定 `"deepseek(search+fetch)"` | _compose_asset 读取；缺省回落 `"gptr-mcp(searxng)"` 保 004 兼容 |

## 成本与重试参数（环境变量，无持久化）

| 变量 | 默认 | 约束 |
|---|---|---|
| `RESEARCH_BACKEND` | `deepseek` | `deepseek`/`gptr-mcp`，非法值报错 |
| `RESEARCH_DS_COUNT` | `8` | 1-50（官方上限） |
| `RESEARCH_DS_FETCH_MAX` | `3` | ≥0，0 = 不补抓 |
| `RESEARCH_DS_RETRIES` | `3` | ≥0，退避 2s/4s/8s |

## 查询词约束

- 长度 > 128 Unicode 字符 → 截断到 128 并记日志（官方 query 上限）
- 空/纯空白 → 管线既有拒绝，先于任何计费调用
