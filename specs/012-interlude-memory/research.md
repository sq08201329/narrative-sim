# Research: 幕间记忆传递

**Date**: 2026-10-21 | **Feature**: 012-interlude-memory

无 NEEDS CLARIFICATION 遗留；以下为关键决策（证据为本地源码实读）。

## R1: 注入点——引擎角色卡 memory 键 + 后端 episodic_memory 双路

- **Decision**: 引擎侧在 `build_scene_config` 的角色 `character` 自由字典加
  `memory` 键；后端侧 `PersonaBackend` 协议新增 `seed_memory(asset_id, text)`，
  TinyTroupeBackend 经 `person.episodic_memory.store({...})` 实现，
  MockPersonaBackend 记录到 `seeded` 列表（spy 供离线断言）。
- **Rationale**: WorldSeed `AgentConfig.character` 官方注释即"free-form, engine
  never reads, given to claiming agent"（config_schema.py:89-90）——加键零引擎
  改动，且进 SceneConfig 校验路径可审计。TinyTroupe 的情景记忆
  `episodic_memory.store` 是其"经历过的事"的原生入口（tiny_person.py:1453），
  注入后参与 act 时的记忆检索，对白自然带上幕经历。
- **Alternatives considered**: 塞进 persona_definitions（beliefs 等）——语义错
  （那是特质不是经历），且会被当成长期人设而非上一幕记忆，否决。
  只注入引擎不注入后端——我们架构里"心智"在 TinyTroupe，引擎卡不进
  visible_state，单引擎路等于没注入，否决。

## R2: 可见性过滤——契约事件三规则，不动 001 枚举

- **Decision**: 事件 E 对角色 C 可见 iff：
  ① `type == "inner_voice"` → 仅 `characters[0] == C`（内心戏私有）；
  ② E 含 `visible_to` 列表（event.schema.json 未设 additionalProperties，
  扩展字段合法）→ 仅 C ∈ visible_to；
  ③ 其余 → 全世界角色（当前单场景全部在场，与 say/act 的 same_location
  scope 同语义）。
- **Rationale**: 契约事件的 type 枚举（dialogue/action/scene_change/narration/
  inner_voice）无私语类型——whisper 目前只存在于引擎动作层，不落契约事件。
  不扩枚举（契约先行，扩枚举是另一个特性的决定）；visible_to 扩展字段为
  未来私语落事件留了合规通道，且本特性测试可用它直接覆盖"定向私语零泄漏"
  （SC-001）。
- **证据**: `schemas/event.schema.json` type 枚举与 additionalProperties 缺省；
  `world.py _map_to_engine_action` 只产 say/act。

## R3: 双通道摘要

- **Decision**: `template` 通道：确定性条目罗列（"第N回合，你说：…/甲
  做了：…"，按 tick 升序）；`llm` 通道：把过滤后事件转写为角色视角的
  自然语言回忆（"你记得…"），走 009 既有的 chat 接缝模式（环境桥接 +
  MODEL_FAST），输入预算 `INTERLUDE_MAX_EVENTS`（默认 50）+ 单条截断，
  超量新近优先。
- **Rationale**: 宪章 IV 要求离线基线；模板通道让全流程（含 MCP）离线可测
  可重复。LLM 通道质量增强，真机验收。
- **成本**: 每角色一次调用；幂等复用使重复生成零调用（FR-005/VI）。

## R4: 幂等与修订——(run_id, asset_id) 当前版 + 表内 revision

- **Decision**: `interlude_memories` 表 (run_id, asset_id, revision) 唯一约束
  另加当前版指针语义：同键 regenerate/修订追加 revision，读取取最新版。
  不复用 asset_revisions（记忆不是资产，来源 run 是其天然维度）。
- **Rationale**: 011 的版本语义（留痕 + 可取历史）同口径复制，但表独立——
  避免把"记忆"硬塞进资产 schema（事件引用、通道、用量都是记忆特有字段）。
- **Alternatives considered**: 复用 asset_revisions（字段不匹配，否决）；
  无版本直接覆盖（违反可审计，否决）。

## R5: 多 run 并存显式指定 + 跨戏交集口径

- **Decision**: `memory_from` 为显式 run_id；目标世界角色与来源 run 角色
  取交集注入，差集在响应 `skipped` 字段标注（FR-009）。
- **Rationale**: 重拍并存时默认猜测必然出错；交集注入让"换人重拍"场景
  （新角色无记忆，老角色带记忆）自然成立。

## R6: 验收口径——真机两幕连跑

- **Decision**: 真机验收用 world_talk.db 既有 run 作上一幕，生成记忆后
  起跑第二幕（TinyTroupe），人工核对下一幕产出引用上一幕经历（SC-002）；
  离线用 spy Mock + 模板通道覆盖全部逻辑断言。
- **Rationale**: 引用上一幕经历是涌现行为，无法离线断言；离线能断的是
  过滤正确性、注入 plumbing、幂等与兼容锚点。
