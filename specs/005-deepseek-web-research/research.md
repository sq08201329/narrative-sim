# Phase 0 Research: DeepSeek Web 调研后端

日期：2026-10-20。API 事实来自官方文档
（api-docs.deepseek.com/zh-cn/guides/search/，上一轮已逐字取得）。

## R1: 检索层实现 — Search 一次 + Fetch 按缺口补抓

**Decision**: `POST {DEEPSEEK_BASE_URL}/v1/tools/search`，
`{"query", "count": RESEARCH_DS_COUNT(默认8), "need_content": true}`。
材料组装：
- `content` 非空的条目：正文直接用
- `content` 为空的条目：`summary`（600-800 字符，官方定位即"给模型阅读"）垫底
- 正文缺失且排序靠前（rerank_score 高）的条目：Fetch 补抓，
  上限 `RESEARCH_DS_FETCH_MAX`（默认 3，成本闸门 FR-005）
- 全部条目既无正文又无摘要、且 Fetch 全失败 → 材料不足，明确失败（FR-006）
- context = 各条目「标题 + URL + 正文/摘要」拼接；source_urls = 全部条目 URL

**Alternatives considered**: 每个条目都 Fetch 全文——Fetch 另计次费且有域名级
限速，summary 已够抽取，只在缺口补抓。

## R2: 子查询规划 — 不做（单查询基线）

**Decision**: 直接用用户查询词做 1 次 Search，不增加"LLM 规划子查询"环节。

**Rationale**: spec Assumptions 已定单查询为基线；DeepSeek Search 的
summary/snippet 已按 query 意图压缩；子查询规划是 GPT-R 为扩召回广度的设计，
会让 Search 计费次数与 LLM 调用翻倍。未来召回质量不足时再单独特性评估。

## R3: 后端选择与默认 — RESEARCH_BACKEND，默认 deepseek

**Decision**: `RESEARCH_BACKEND=deepseek|gptr-mcp`，未设默认 `deepseek`
（零常驻服务、无限流痛点的那条腿优先）；非法值明确报错。
`research.py` 的 `_default_call_tool()` 改为按后端分发：
- `gptr-mcp`：现有 MCP 路径不变（FR-008）
- `deepseek`：新工厂返回同签名 `call_tool(name, arguments)`，忽略 name，
  用 `arguments["query"]` 执行 R1 流程，返回 deep_research 同形态 dict
  （`status/context/sources/source_urls`）+ `retriever` 键

**溯源标识**：`call_tool` 返回 dict 可带 `retriever` 键；`_compose_asset`
改为 `resp.get("retriever", "gptr-mcp(searxng)")`——gptr-mcp 路径行为
逐字节不变（FR-008 兼容），DeepSeek 后端标识为 `deepseek(search+fetch)`。

## R4: 错误语义（FR-004，对齐官方错误表）

| 情形 | 行为 |
|---|---|
| 429 / 408 / 5xx | 指数退避重试（2s/4s/8s），上限 `RESEARCH_DS_RETRIES`（默认 3） |
| 402 | `ResearchError("DeepSeek 余额不足")`，不重试 |
| 其它 4xx（400/401/403/404/413） | 不重试，明确报错（403/404 仅 Fetch：跳过该源） |
| Search results 空 | 返回 success + 空 source_urls → 管线既有「无来源拒绝」路径（FR-006） |
| Fetch 403/404 | 跳过该 URL 继续下一个；全部失败才按材料不足报错 |

## R5: 成本闸门（FR-005）

| 变量 | 含义 | 默认 |
|---|---|---|
| `RESEARCH_BACKEND` | 后端选择 | `deepseek` |
| `RESEARCH_DS_COUNT` | Search 返回条数（≤50） | `8` |
| `RESEARCH_DS_FETCH_MAX` | Fetch 补抓次数上限 | `3` |
| `RESEARCH_DS_RETRIES` | 退避重试上限 | `3` |

单次调研成本上限 = 1 次 Search + 3 次 Fetch，可预期。
复用：`DEEPSEEK_BASE_URL`/`DEEPSEEK_API_KEY`（端点与密钥零新增，FR-003）。

## R6: 边界口径

- query > 128 字符：截断到 128（官方上限），截断行为记日志（spec Edge Case
  选定口径：截断而非拒绝——查询词通常是自然语言，截断损失可接受）
- 空/纯空白查询：管线既有拒绝逻辑在 Search 之前生效，不产生计费调用
- Fetch URL 校验（必须 http/https 含 host）：Search 返回的 URL 天然合法，不另校验

## R7: 测试策略（FR-007，离线 Mock 基线）

- mock httpx 层：Search/Fetch 响应体、状态码序列（429→200、402、5xx×N）
- 后端选择器：env 各值 → 正确工厂；非法值报错；未设默认 deepseek
- 材料组装：content 缺失 → summary 垫底 → Fetch 补抓次序与上限；
  全缺 → 材料不足报错
- retriever 标识：deepseek 路径 `deepseek(search+fetch)`，
  gptr-mcp 路径保持 `gptr-mcp(searxng)`（兼容断言）
- 004 既有 17 项测试保持绿（FR-008）

## R8: 依赖与回归面

- 零新增依赖（httpx 已在 lock，原则 V）
- 改动面：`orchestrator/research.py`（DeepSeek 后端 + 选择器 + retriever 键）、
  `tests/contract/test_research_pipeline.py`（新用例）、`.env.example`
- gptr-mcp 代码路径行为不变（R3 兼容设计），M1/M2/003/004 回归兜底
