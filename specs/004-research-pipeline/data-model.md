# Data Model: 自动资产调研管线

本特性不改资产/事件契约（FR-009）。以下为运行时概念模型与既有契约字段的填充口径。

## 调研请求（ResearchRequest，运行时，无持久化）

| 字段 | 类型 | 来源 | 校验 |
|---|---|---|---|
| query | str | CLI `--query` | 空/纯空白直接拒绝（Edge Case），不发起外部调用 |
| asset_type | enum | CLI `--type` | `character/prop/scene/epoch` 四选一 |
| timeout_s | int | `RESEARCH_TIMEOUT_S` | 默认 180，MCP 长调用超时 |

## 调研来源（ResearchSource，随资产持久化）

来源 = gptr-mcp `deep_research` 返回的 `source_urls` 与 `sources`（服务端已完成
检索与抓取，客户端不自抓网页）。落库形态：`historical_context.sources` =
source_urls 数组，非空才允许入库（FR-002）。`context`（压缩后的调研材料）
仅运行时用于结构化抽取，抽取后即弃。

## 资产草稿（AssetDraft，运行时中间态）

对 deep_research 返回的 context 做 LLM 抽取的产物，经 `store.put_asset()` 的 schema 校验后才成为库中资产。
校验失败 → 重试 1 次 → 仍失败则报错零写入（FR-003）。

契约字段填充口径（research.md R4/R8）：

| 契约字段 | 填充 |
|---|---|
| asset_id | `{prefix}_{sha1(name)[:10]}`，prefix 由 type 映射 char/prop/scene/epoch |
| provenance.retriever | `"gptr-mcp(searxng)"` |
| provenance.model | 实际抽取用模型名（llm tier 对应模型） |
| provenance.researched_at | ISO8601 时间戳 |
| provenance.confidence | `min(0.5 + 0.1 × 成功来源数, 0.9)` |
| historical_context.sources | deep_research 的 source_urls |
| 其余（appearance / persona_spec / …） | LLM 按类型指引抽取 |

## 去重判定（DedupDecision，运行时）

- 比较文本：`name + appearance.description/visual_prompt`（取存在的字段拼接）
- 范围：同 `type` 的库中资产（`store.list_assets(type)`）
- 判定：余弦 ≥ `RESEARCH_DEDUP_THRESHOLD`（默认 0.85）→ 重复，
  返回已有 asset_id，零写入（FR-004）
- 降级：嵌入不可用 → name 精确匹配 + 降级日志（FR-005）
- 向量维度 768（沿用 003），现算不缓存
