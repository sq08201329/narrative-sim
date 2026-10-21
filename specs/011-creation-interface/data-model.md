# Data Model: 创作队对接接口

**Date**: 2026-10-21 | **Feature**: 011-creation-interface

## 新增表：asset_revisions（db/init_db.py）

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | |
| asset_id | TEXT NOT NULL REFERENCES assets(asset_id) | |
| revision | INTEGER NOT NULL | 0 = 调研原版，单调递增 |
| payload | TEXT NOT NULL | 该版完整资产快照 JSON |
| patch | TEXT | 本版相对上版的 merge patch JSON（rev 0 为 NULL） |
| reason | TEXT NOT NULL DEFAULT '' | 修订理由 |
| author | TEXT NOT NULL DEFAULT 'system' | 修订者（agent 标识/retriever 标签） |
| created_at | TEXT NOT NULL DEFAULT (datetime('now')) | |

约束：`UNIQUE(asset_id, revision)`；索引 `idx_revisions_asset ON
asset_revisions(asset_id)`。

## 既有表变更：assets

- 新增列 `current_revision INTEGER NOT NULL DEFAULT 0`（当前版指针）。
- 幂等迁移：init_db 对老库 `PRAGMA table_info(assets)` 检测后
  `ALTER TABLE ADD COLUMN`；asset_revisions 为 CREATE TABLE IF NOT EXISTS。
- 不变量：`assets.payload` == `asset_revisions[current_revision].payload`。

## 世界 config 扩展（worlds.config JSON，键级增量）

```json
{
  "character_ids": ["char_a"],
  "location_id": "scene_x",
  "revisions": {"char_a": 2, "scene_x": 0},
  "created_at": "..."
}
```

- `revisions` 为版号锚点（FR-008）；旧 config 无此键 → 按当前版取卡
  （向后兼容，R4）。
- reshoot(use_latest=True) 重钉该映射并更新 config。

## 移交目录布局（orchestrator/handoff.py 产出，不落库）

```text
handoff/<world_id>/
├── manifest.json      # 自描述清单（见下）
├── assets/<asset_id>.json      # 资产全字段（含 secret，带密级键）
├── events.jsonl       # 事件流（run_id 指定或该世界最近 run）
├── world.json         # 最新世界快照（tick + state）
├── dm_calls.json      # 裁决台账（无裁决为空数组）
├── materials/<asset_id>.md     # 调研原料原文（每资产一个文件）
└── sources.md         # 溯源汇总（资产 provenance + 原料来源）
```

manifest.json：

```json
{
  "format": "narrative-sim-handoff/1",
  "world_id": "...", "run_id": "...", "generated_at": "...",
  "revision_pins": {"char_a": 2},
  "items": [{"path": "assets/char_a.json", "kind": "asset",
             "sha256": "...", "bytes": 1234}],
  "secrecy": "assets/*/persona_spec.secret 与 world.json 中 secret 为创作可见、仿真角色不可见信息",
  "counts": {"assets": 3, "events": 25, "dm_calls": 4, "materials": 3}
}
```

## 既有实体复用（零改动）

- events / runs / dm_calls / research_materials / worlds.state：全部只读复用。
- 事件 append-only、原料只进不出、config 冻结——三冻结面（FR-009）无表结构
  变更，靠修订层代码路径保证（测试断言）。

## 状态流转

资产版号：`0（调研原版）→ 1 → 2 …`（revise）单调递增；rollback 只动
`current_revision` 指针不删行；同一资产并发修订以 base_revision 乐观锁
裁决（RevisionConflict）。
