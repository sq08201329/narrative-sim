# Phase 1 Data Model: uv 项目脚手架与最小仿真链路（M1）基线

实体口径以手册 3.1 / 3.2 为准；完整约束见 `contracts/asset-event-schemas.md`。

## 实体

### Asset（资产）

| 字段 | 类型 | 约束 |
|------|------|------|
| `asset_id` | string | 主键；pattern `^(char|prop|scene|epoch)_[a-z0-9_]+$` |
| `type` | string | 枚举 `character / prop / scene / epoch` |
| `name` | string | 必填，非空 |
| `appearance` | object | 外貌/服饰/道具描述，含 `visual_prompt`；character 必填 |
| `persona_spec` | object | character 必填：`age / occupation / personality / beliefs / speech_style` |
| `historical_context` | object | 时代、地域、`sources`（来源 URL 列表） |
| `reference_images` | array | 参考图路径/URI |
| `provenance` | object | 必填：`researched_at / retriever / model / confidence` |
| `status` | string | 枚举 `draft / verified / deprecated`，默认 `draft` |

### Event（事件）

| 字段 | 类型 | 约束 |
|------|------|------|
| `event_id` | string | 主键；pattern `^e[0-9]{4,}$` |
| `run_id` | string | 必填；关联 Run |
| `tick` | integer | ≥ 0；0 为场景建立帧 |
| `seq` | integer | ≥ 0；回合内序号 |
| `type` | string | 枚举 `dialogue / action / scene_change / narration / inner_voice` |
| `characters` | array | 只含 asset_id 引用，不放外貌文本 |
| `location` | string | scene 类资产 ID |
| `content` | string | 事件文本 |
| `emotion` | string | 可空 |
| `cause_refs` | array | 上游 event_id 列表 |
| `shot_hint` | object | `camera / duration_s / style` |
| `created_at` | string | ISO 8601 时间戳 |

### Run（一次仿真运行）

| 字段 | 说明 |
|------|------|
| `run_id` | 主键 |
| `world_id` | 关联 World |
| `status` | `running / done / failed`，默认 `running` |
| `token_cost` | 按 run_id 聚合的 token 成本（M1 恒为 0） |
| `started_at` / `ended_at` | 起止时间 |

### World（世界状态）

| 字段 | 说明 |
|------|------|
| `world_id` | 主键 |
| `config` | 世界配置（M1 为占位空串） |
| `state` | 每回合状态快照（M1 可为空，M4 起必填） |
| `tick` | 当前回合数，默认 0 |

## 关系

```
World 1 ──< Run 1 ──< Event
Asset （被 Event.characters / Event.location 以 asset_id 引用）
```

## 存储映射（SQLite 4 表）

`assets` / `worlds` / `runs` / `events`，主键如上；`payload` 列存完整 JSON；
建表幂等（`CREATE TABLE IF NOT EXISTS`）；`events` 建 `(run_id, tick, seq)` 索引。

## 校验规则

- 入库（`put_asset` / `put_event`）与导出前，逐条经对应 JSON Schema 校验；
  失败即拒绝，错误信息含字段路径（见 research.md D6）
- 事件排序键：`run_id → tick → seq`
- 状态流转：`Asset.status: draft → verified → deprecated`（本特性不实现流转接口，
  仅落字段）；`Run.status: running → done / failed`
