# Phase 0 Research: 接入 WorldSeed 世界引擎

日期：2026-10-20。全部结论经本地副本源码核实（子代理调查，行号见各节）；
本项目的 simulation.py / store.py 接缝已同步核实。

## R1: 总体形态 — WorldSeed 是被动式世界引擎，与我们的角色后端天然互补

**核心事实**: WorldSeed 自己不驱动 agent 思考——agent 是外部代码经
`perceive()` 拉视野、`submit()` 推动作。引擎内唯一 LLM 调用点是 DM（裁判），
且 DMProvider 是可注入 Protocol。

**Decision**: TinyTroupe（002 真后端）继续担任角色智能体，WorldSeed 接管
世界状态与规则（FR-003 单一真相源）。每回合：引擎 `perceive(agent_id)` →
组装 visible_state → `backend.act()` → 动作映射回引擎 `submit()` → `step_async()`。
002 的适配器与资产沉淀全部保留，耦合面只有五件套
（`WorldEngine(config)` / `register_agent` / `perceive` / `submit` / `step_async`，
world.py:256/374/415/454）。

**Alternatives considered**: 引擎原生 Agent 承载（丢掉 TinyTroupe）——
002 的人格记忆/语义记忆投资作废，否；openclaw-plugin 外部 runtime——
自家角色后端已够用，不需要。

## R2: 世界配置组装（FR-001）

**Decision**: 适配器从资产库生成 SceneConfig（YAML 的内存对象形态）：
- 场景资产 → `scene:` + `entities:`（房间/物品平铺属性）
- 角色资产 → `agents:`：`character:` 卡（identity/personality/goals 来自
  persona_spec，**secret 字段**承载私密信息）
- 信息不对称（US1-AC2）→ `perception:` 段：`hidden_properties: ["secret", "goals"]`
  + visibility DSL + event_scopes
  （configs/teahouse.yaml:245-255 为模板；schema 全量见 configs/SCENE_CONFIG.md）
- 动作集 `actions:`：先提供基础动作（say/move/inspect 等机械效果动作，
  模板化自 teahouse.yaml）

**机制证据**: 人物卡（含 secret）存 AgentRegistry，只有 DM prompt builder 能读，
Perceiver/Inbox 永不接触（ARCHITECTURE.md:72-76）；`load_stripped_config()`
系统性剥除 hidden 属性（world.py:155-204）——信息不对称是引擎内置能力，
我们只需正确配置。

## R3: DM（裁判）— MVP 不启用，自实现 DMProvider 留作后续

**Decision**: 本特性生成的动作集**不含 DM 动作**（全部机械效果），
dm_provider 用引擎自带 Mock（dm/providers/mock.py）。

**Rationale**: DM 输出是嵌套 EffectConfig DSL，deepseek-flash 级模型翻车率
可观；引擎的 LiteLLM DM 走 instructor TOOLS 模式（DeepSeek 可兼容）但引入
litellm+instructor extra 且默认 10s 超时。机械效果已满足 spec 三个故事
（信息不对称、快照、翻译都与 DM 无关）。自实现 DMProvider（5 行 judge()
调 llm.chat_json）是干净的后续增量，接口证据 dm/providers/base.py:13-21。

## R4: 快照与断点续跑（FR-004/FR-005）

**Decision**: 每 tick 后调 `engine.save_state()`（world.py:635）序列化为 JSON，
经 **store.py 新增** `put_world_state(world_id, tick, state)` /
`get_world_state(world_id)` 写入 worlds.state（原则 III 单一入口；
store 现有 worlds 行由 create_run 自建的接缝）。
续跑：同配置重建引擎 → `engine.load_state(...)`（world.py:648）→ 从
snapshot_tick+1 继续；事件编号经既有 `store.max_event_no()` 天然连续（002 模式）。

**避开**: 引擎的 RunRecorder（事件溯源落 ~/.worldseed/ 不可配路径）——
用 NullRecorder 默认 + 我们自己的 worlds.state 即可。
已知坑记录：transient 不含 pending_ops（暂停时 GM 队列丢失，
state-persistence.md:268）——我们的回合模型是"回合外提交、回合内结算"，
快照点在回合结算后，队列恒空，不受影响。

## R5: 事件翻译（FR-002，复用 001 口径）

**Decision**: 契约事件来源两级：
1. 角色动作：backend.act 返回（kind/content/emotion）→ 与 001 完全相同的
   emit 逻辑与 `_SHOT_BY_KIND` 映射（对话框/内心/动作）
2. 引擎侧：EventLog 的 scope=global 重要事件（如场景/实体状态显著变化）→
   `scene_change`/`narration` 事件
visible_state 由 `AgentPerception`（self_state/nearby_entities/events/
whispers，protocol/agent.py:23-43）组装为 backend 既有的
{tick, location, recent_events} 键——**backend 接口零改动**（002 适配器、
001 Mock 都直接可用）。

## R6: 模块布局与入口（原则 II/IV）

- `orchestrator/world.py`：WorldSeed 全部接触面（配置组装、引擎生命周期、
  perceive/submit/step 循环、快照读写、翻译）—— 一个新适配器模块
- `orchestrator/simulation.py`：**不改**（M1/M2 基线原样保留，FR-007）；
  世界循环在 world.py 内，CLI 指向它
- `scripts/run_world_chain.py`：新 CLI（--world-id --ticks --db --resume），
  结构对照 run_real_chain.py（cwd 守卫 / 打印 / 验收口径）
- `orchestrator/store.py`：仅加 `put_world_state` / `get_world_state` 两个方法
- 离线测试：**真实引擎 + MockBackend**（引擎本身离线可跑，机械动作无需 LLM）
  —— 比纯 mock 更强的基线：配置组装/信息不对称/快照续跑全部真引擎验证

## R7: 依赖与安装（原则 V）

**Decision**: `uv add --editable /d/kimicode_repos/projects/my_mas/WorldSeed`
（本地副本路径安装；MIT 许可，pyproject hatchling 打包 src/worldseed）。

- requires-python >=3.11 ✅；无编译型依赖，全平台纯 Python
- 硬依赖含 fastapi/uvicorn/anthropic（无谓重量但无害；anthropic 仅
  autoresearch/ 引用，我们不 import）
- 不装 `dm` extra（litellm/instructor，R3 已决定绕开）
- 避开两个坏特性：`worldseed run`（缺 scripts/worldseed_agent.py）与
  `scene.use` presets（目录不存在）——我们只用库 API

## R8: 环境变量（原则 VI）

复用既有（DEEPSEEK_*、EMBEDDING_*）。本特性新增倾向零：
引擎配置由资产库组装、DM 不启用、无外部服务。
若实现中确需新增（如动作集模板路径），随 tasks 评审补记。

## R9: 回归面

- M1/M2 链路代码零改动（simulation.py / run_*_chain.py 不动）
- store.py 只加读两个方法，既有 14 个方法签名不变
- 新链路的离线测试纳入 `-m "not real"` 套件（真实引擎+MockBackend，无 LLM）
- 真机验收：DeepSeek 密钥 + TinyTroupe 后端跑世界链路（成本同 002 量级）
