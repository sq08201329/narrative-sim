# Data Model: 立项调研纲领与原料入库

本特性不改资产/事件契约（素材类不做资产化，type 枚举不扩列）。

## 调研纲领（Brief，JSON 文件，异步审阅）

```json
{
  "theme": "题材文本",
  "generated_at": "ISO8601",
  "items": [
    {"category": "world",     "query": "南宋临安城市布局与市井生活",
     "asset_type": "epoch"},
    {"category": "character", "query": "宋代游方女医者",
     "asset_type": "character"},
    {"category": "lore",      "query": "南宋临安治安与缉捕制度",
     "asset_type": null, "link": null}
  ]
}
```

- `category` 三值：`world` / `character` / `lore`（剧情素材）
- 资产类（world/character）必有 `asset_type`（character/scene/prop/epoch）；
  素材类（lore）`asset_type=null`，可选 `link`（挂载资产 id）
- 条数 ≤ `BRIEF_MAX_ITEMS`（默认 12），每类 ≥1 条

## 执行总账（Ledger，运行时 + CLI 打印）

```json
{"item": {"query": "...", "category": "..."},
 "status": "stored|deduplicated|reused|cached|merged|attached|failed",
 "asset_id": "char_xxx 或 null", "reason": "失败原因或 null"}
```

status 语义：stored 新入库 / deduplicated 004 去重命中 / reused FR-011 高阈值
跳过 / cached FR-009 精确缓存命中 / merged FR-010 清单内合并 /
attached 中阈值调研后原料挂已有资产 / failed 失败（reason 必填）。

## 调研原料（research_materials 表，持久化）

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| asset_id | TEXT | 挂载资产（lore 可为 `lore:<题材 slug>`） |
| query | TEXT | 调研查询词（精确缓存键） |
| retriever | TEXT | 检索链标识（与 provenance 同口径） |
| context | TEXT | 原料原文，≤ `RESEARCH_MATERIAL_MAX_CHARS`（默认 8000） |
| created_at | TEXT | 默认当前时间 |

追加语义：同 asset_id 可挂多条（素材只增不减，FR-005）；
`get_material_by_query` 取该查询词最新一条。

## 漏斗参数（环境变量）

`RESEARCH_SKIP_THRESHOLD`（0.88，复用跳过）、
`RESEARCH_ATTACH_THRESHOLD`（0.80，attach 区间下限）、
`BRIEF_MAX_ITEMS`（12）、`RESEARCH_MATERIAL_MAX_CHARS`（8000）。
嵌入不可用 → ③④层降级为名称精确匹配（与 004 同语义）。
