# Data Model: 幕间记忆传递

**Date**: 2026-10-21 | **Feature**: 012-interlude-memory

## 新增表：interlude_memories（db/init_db.py）

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | |
| run_id | TEXT NOT NULL REFERENCES runs(run_id) | 来源幕 |
| asset_id | TEXT NOT NULL REFERENCES assets(asset_id) | 角色 |
| revision | INTEGER NOT NULL DEFAULT 1 | 同键递增（regenerate/修订留痕） |
| summary | TEXT NOT NULL | 记忆摘要文本（角色视角） |
| event_refs | TEXT NOT NULL | 事件 id 列表 JSON（过滤后的可感知集） |
| channel | TEXT NOT NULL | "template" / "llm" |
| tokens_in | INTEGER NOT NULL DEFAULT 0 | llm 通道用量 |
| tokens_out | INTEGER NOT NULL DEFAULT 0 | |
| created_at | TEXT NOT NULL DEFAULT (datetime('now')) | |

约束：`UNIQUE(run_id, asset_id, revision)`；
索引 `idx_interlude_run ON interlude_memories(run_id, asset_id)`。

读取语义：同 (run_id, asset_id) 取 MAX(revision) 为当前版。

## 过滤规则（记忆生成的输入集）

事件 E 对角色 C 可见 iff：

1. `type == "inner_voice"` → 仅当 `characters[0] == C`（内心私有）
2. E 含 `visible_to` 扩展字段（list[str]）→ 仅当 C ∈ visible_to
3. 其余 → 全世界角色公开

## 注入载体（不落库，装配期生效）

- **引擎侧**：SceneConfig 角色 `character.memory` 键（自由字段，
  引擎不读；进 config 校验与审计路径）
- **后端侧**：`backend.seed_memory(asset_id, summary)`；TinyTroupe 经
  `episodic_memory.store`；Mock 记录到 `seeded` 列表

## 世界 config 扩展（键级增量）

```json
{"character_ids": [...], "location_id": "...", "revisions": {...},
 "memory_from": "run_id_or_null"}
```

仅记录来源幕标识；记忆内容以 interlude_memories 表为准（单一真相源）。

## 既有实体复用（零改动）

- events（过滤源，只读）、assets/worlds/runs（011 既定）、
  asset_revisions（角色卡修订与记忆修订互相独立）。
