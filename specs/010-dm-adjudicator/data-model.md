# Data Model: DM 裁判启用

**Date**: 2026-10-21 | **Feature**: 010-dm-adjudicator

## 新增表：dm_calls（db/init_db.py）

裁决审计表，每次引擎裁决调用（成功或失败）一行。唯一写入点
`store.put_dm_call`，读取点 `store.list_dm_calls`。

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PRIMARY KEY | 自增 |
| run_id | TEXT NOT NULL | 所属 run（外键引用 runs(run_id)，与 events 同口径） |
| tick | INTEGER NOT NULL | 发生 tick |
| action | TEXT NOT NULL | 被裁决的动作类型（当前恒为 act） |
| agent_id | TEXT NOT NULL | 行动角色资产 id |
| params | TEXT NOT NULL | 动作参数 JSON |
| hint | TEXT | 裁决提示 |
| narrative | TEXT | 裁决叙事（失败时为兜底说明） |
| effects | TEXT NOT NULL | 效果列表 JSON（校验后实际生效的） |
| tokens_in | INTEGER NOT NULL DEFAULT 0 | 输入 token |
| tokens_out | INTEGER NOT NULL DEFAULT 0 | 输出 token |
| elapsed_s | REAL NOT NULL DEFAULT 0 | 裁决耗时秒 |
| failed | INTEGER NOT NULL DEFAULT 0 | 0=成功 1=失败（走降级） |
| created_at | TEXT NOT NULL DEFAULT (datetime('now')) | 落库时间 |

索引：`idx_dm_calls_run ON dm_calls(run_id)`。

## 配置对象：DMOptions（orchestrator/world.py，内存对象不落库）

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| hint | str | "判定该动作在世界中的结果：成败、后果、对他人的可感知影响。" | DMConfig.hint |
| allowed_ops | list[str] | ["set","increment","decrement","emit_event"] | 效果操作符白名单 |
| max_effects | int | 5 | 单次裁决效果上限 |
| knowledge_chars | int | 2000 | 史料注入字符预算 |
| max_calls | int | 50 | scene.max_dm_calls 成本帽 |
| model | str | env MODEL_FAST 或 "deepseek-flash" | 裁决模型 |
| timeout_s | float | 30.0 | 单次裁决超时 |
| max_retries | int | 2 | instructor 校验重试 |

## 既有实体复用（零改动）

- **research_materials**（009）：史料注入只读来源，经 `store.get_materials`。
- **DMContext / DMResponse / DMConfig**（引擎）：契约数据结构，本特性不扩展字段。
- **worlds.state 快照**：裁决效果引起的状态变更由引擎 save_state 自然覆盖，
  快照格式不变（resume 兼容）。

## 状态流转

裁决结果无独立状态机；生命周期为：动作提交 → 裁决（成功|失败）→
效果入世界状态（成功且合法时）→ dm_calls 审计行落库。失败行 `failed=1` 且
effects 为 `[]`，与成功行可区分、可统计。
