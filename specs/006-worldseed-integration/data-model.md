# Data Model: 接入 WorldSeed 世界引擎

本特性不改资产/事件契约（FR-007）。以下为运行时概念模型与持久化口径。

## 世界配置（SceneConfig，由资产库组装，运行时 + worlds.config 留存）

| 段 | 来源 | 口径 |
|---|---|---|
| scene | 场景资产 | id = asset_id，description 取 appearance.description |
| entities | 场景资产 | 房间/物品实体，平铺属性（引擎平铺字符串属性模型） |
| agents[].character | 角色资产 persona_spec | identity/personality/goals；**secret 字段**承载私密信息 |
| actions | 适配器模板 | 机械效果动作（say/move/inspect 等，无 DM 段） |
| perception | 适配器模板 | `hidden_properties: ["secret", "goals"]` + visibility DSL + event_scopes |
| auto_tick | 适配器模板 | 关（回合由我们的循环显式推进） |

## 引擎回合产出（运行时）

- `ActionResult`（success/action/reason）：submit/step 的动作结算回执
- `Event`（tick/type/source/detail/ttl/scope/push/highlight）：引擎事件日志条目，
  scope=global 的重要条目可翻译为契约 scene_change/narration 事件
- `AgentPerception`（self_state/nearby_entities/nearby_agents/events/whispers/
  action_options）：每角色每回合的过滤视野 —— 组装 backend visible_state
  （{tick, location, recent_events} 键）的唯一来源（FR-003）

## 世界状态快照（持久化，worlds.state）

- 内容：`engine.save_state()` 的 JSON 序列化（实体属性 + tick + 角色卡）
- 写入：每 tick 结算后 `store.put_world_state(world_id, tick, state_json)`
- 读取：续跑时 `store.get_world_state(world_id)` → `(tick, state)`，
  同配置重建引擎后 `load_state(...)`，从 tick+1 继续
- 事件编号：跨续跑经 `store.max_event_no()` 连续（002 模式，天然满足 FR-005）

## 契约事件（翻译产物，形态同 001）

- 角色动作（dialogue/inner_voice/action）← backend.act 返回，emit 逻辑与
  `_SHOT_BY_KIND` 映射复用 001 逐字节口径
- scene_change/narration ← 引擎 scope=global 重要事件（可选，MVP 至少保留
  开场场景事件与 001 同形态）

## 断点续跑边界

- 快照点在回合结算后：引擎动作队列恒空（回合外提交、回合内结算），
  不受引擎 transient 不含 pending_ops 已知坑影响
- 快照损坏/反序列化失败：续跑明确报错，不以损坏状态继续（Edge Case）
- 同一 world_id 已有快照时新跑：显式重置或拒绝（与 002 真链路 reset 同口径）
