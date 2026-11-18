# Contracts: 故事时间树

## CLI：`narrative timeline`

```text
narrative timeline import T001 --story story.txt [--overwrite]
narrative timeline show T001
narrative timeline drive T001 --stage research
narrative timeline drive T001 --stage world --world-id W001
narrative timeline drive T001 --stage run --run-id R001 [--ticks N] [--backend mock|tinytroupe]
narrative timeline export T001 --out timeline.json
```

- `import`：读取 UTF-8 纯文本，抽取 + 四项自查，通过后写库并返回 JSON（tree_id/status/node_count/checks）。失败非零退出、不写库。重复 tree_id 需 `--overwrite`。
- `show`：返回树内容（`nodes` / `entities` / `asset_map` / `node_worlds` / `run_nodes`）与最近一次 `self_check`。
- `drive --stage research`：实体去重后经 `brief.execute_brief` 四层漏斗，返回 ledger；回填 `entity_assets`。
- `drive --stage world`：按空间节点建世界，回填 `node_worlds`，返回世界列表。
- `drive --stage run`：对每世界按 tick 均分节点，事件带 `node_id`；返回 run 列表与事件数。未 ready 树直接拒绝。世界多于一个时，每个世界派生一个 run_id：`{base}__{node_id}`（base 即 `--run-id`），结果以 `runs` 列表返回；仅一个世界时直接用 base。
- `timeline export`：导出树 JSON 到文件（与既有 `narrative export R001` 事件导出不同）。
- 冻结版把 `narrative` 换为 `NarrativeSim.exe`，参数一致。

## MCP 工具（薄封装，业务逻辑只在 orchestrator/workflows.py）

| 工具 | 参数 | 行为 |
|---|---|---|
| `import_timeline` | tree_id, story_text, overwrite? | 调 `workflows.import_timeline` |
| `show_timeline` | tree_id | 调 `workflows.show_timeline` |
| `drive_timeline` | tree_id, stage, world_id?, run_id?, ticks?, backend? | 调 `workflows.drive_timeline` |

MCP 只做参数转发与 `_fail` 错误包装，不直连 store、不写业务逻辑。

## Schema：`schemas/story_tree.schema.json`（草稿字段）

```json
{
  "type": "object",
  "required": ["tree_id", "status", "source_sha256", "created_at", "checked_at",
               "entities", "nodes", "self_check"],
  "properties": {
    "tree_id": {"type": "string", "pattern": "^T[0-9]{3,}$"},
    "status": {"const": "ready"},
    "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "entities": {"type": "array", "items": {
      "required": ["key", "type", "name"],
      "properties": {
        "key": {"pattern": "^(char|scene|prop)_[a-z0-9_]+$"},
        "type": {"enum": ["character", "scene", "prop"]},
        "name": {"minLength": 1}
      }}},
    "nodes": {"type": "array", "minItems": 1, "items": {
      "required": ["node_id", "ord", "parent_node_id", "text_time",
                   "location_key", "character_keys", "prop_keys", "event", "source_span"],
      "properties": {
        "node_id": {"pattern": "^n[0-9]{4,}$"},
        "ord": {"type": "integer", "minimum": 1},
        "parent_node_id": {"type": ["string", "null"]},
        "text_time": {"type": ["string", "null"]},
        "location_key": {"type": ["string", "null"]},
        "character_keys": {"type": "array"},
        "prop_keys": {"type": "array"},
        "event": {"required": ["type", "summary"],
                  "properties": {
                    "type": {"enum": ["dialogue","action","scene_change","narration","inner_voice"]},
                    "summary": {"minLength": 1}}},
        "source_span": {"required": ["start", "end", "quote"],
                        "properties": {
                          "start": {"type": "integer", "minimum": 0},
                          "end": {"type": "integer", "exclusiveMinimum": 0},
                          "quote": {"minLength": 1}}}
      }}},
    "self_check": {"required": ["passed", "checks", "checked_at"],
                   "properties": {
                     "passed": {"const": true},
                     "checks": {"type": "array", "minItems": 4},
                     "checked_at": {"type": "string"}}},
    "entity_assets": {"type": "object"},
    "node_worlds": {"type": "object"},
    "run_nodes": {"type": "object"}
  }
}
```

## Event 契约变更

`event.schema.json` 增加可选字段：

```json
"node_id": {"type": "string", "pattern": "^n[0-9]{4,}$"}
```

既有事件无此字段仍通过校验；树驱动 run 的事件必须带合法 `node_id`（SC-004）。
