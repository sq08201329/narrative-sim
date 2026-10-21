# Research: DM 裁判启用

**Date**: 2026-10-21 | **Feature**: 010-dm-adjudicator

本特性无 NEEDS CLARIFICATION 遗留；以下为关键技术决策的调研结论（证据均为
本地源码实读）。

## R1: 裁决提供者——复用引擎自带实现，不自写

- **Decision**: 使用 `worldseed.dm.providers.llm.LiteLLMDMProvider`，不自行实现
  DMProvider 协议。
- **Rationale**: 该类已完整实现契约——instructor 结构化输出（`DMJudgment`：
  narrative + effects，Pydantic 校验失败自动把错误回注 LLM 重试）、主备模型
  降级、token 统计、结构化日志（`dm_llm_call_ok/failed`）。自写只能做出它的
  子集，且违反"最小新代码"。
- **Alternatives considered**: 自实现 `judge()`（裸 openai SDK + JSON 解析）——
  重试/校验/审计都要自己写，约 3 倍代码量，无收益，否决。
- **证据**: `my_mas/WorldSeed/src/worldseed/dm/providers/llm.py` 全文。

## R2: 模型通道——openai/ 前缀 + 环境桥接，零新密钥

- **Decision**: 模型串 `openai/{MODEL_FAST}`（MODEL_FAST 默认 `deepseek-flash`）；
  仅存在 `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL` 时桥接为 `OPENAI_API_KEY`/
  `OPENAI_BASE_URL`（002 既有模式）；litellm openai provider 原生读这两个变量。
- **Rationale**: 与 persona_tinytroupe 走同一出口同一密钥，满足宪章 VI 单一
  通道；无需引入 litellm 的 deepseek provider 配置（它要求 `DEEPSEEK_API_KEY`
  但 base url 固定，灵活性反而差）。
- **Alternatives considered**: `deepseek/deepseek-chat` 原生 provider——base_url
  不可经既有桥接覆盖，与 002/005 通道不一致，否决。

## R3: 裁决范围——仅 act 动作，场景级显式开关

- **Decision**: `build_scene_config` 增加可选 `dm: DMOptions` 参数；仅当非 None
  时给 `act` 动作挂 `DMConfig`（hint/allowed_ops/max_effects）并设置
  `scene.dm_knowledge`、`scene.max_dm_calls`。`say`/`whisper` 永不挂裁决。
- **Rationale**: `ActionConfig.dm` 是引擎既定的逐动作裁决声明位；对话类动作是
  确定性通讯（引擎直接按事件模板分发），裁决只会增加成本与不确定性。开关
  默认关 → 向后兼容（FR-003）。
- **证据**: `config_schema.py` DMConfig(L252)/ActionConfig.dm(L287)/
  SceneMetaConfig.dm_knowledge(L444)/max_dm_calls。

## R4: 史料注入——scene.dm_knowledge，预算截断

- **Decision**: 新增 `build_dm_knowledge(store, asset_ids, budget=2000)`：对参与
  角色 + 场景资产逐一 `store.get_materials(asset_id)`，每条原料渲染为
  `【query】context前N字`，拼接到预算上限，超长丢弃尾部整条；无原料返回 ""。
- **Rationale**: 引擎原生把 `scene.dm_knowledge` 放进 DMContext.dm_knowledge
  （builder.py L59），且注明"not visible to agents"——正是史料该在的位置。
  字符预算防止挤占世界状态上下文（FR-007）。
- **Alternatives considered**: 语义检索排序（003 嵌入服务）——当前原料量级
  （每资产个位数条）用不上，等量级上来再开特性，否决。

## R5: 审计落库——捕获引擎 dm_call 记录

- **Decision**: `_CaptureRecorder` 增加 `record(kind, tick, **data)`：捕获
  `kind == "dm_call"` 的记录到内存缓冲；`run_world` 结束后逐条
  `store.put_dm_call(run_id, ...)`。新表 `dm_calls`（字段与引擎 record 载荷
  对齐：tick/action/agent_id/params/hint/effects/narrative/tokens/elapsed/failed）。
- **Rationale**: 引擎在成功与失败路径都调用 `recorder.record("dm_call", ...)`
  （dm_resolver.py L185-215），这是现成的审计钩子；我们既有 _CaptureRecorder
  本来就为"引擎 recorder 接口不可配路径"而存在（006 R4），顺势扩展。
- **Alternatives considered**: 解析 structlog 日志——脆、非结构化落库，否决。

## R6: 成本帽——引擎原生 max_dm_calls + 提供者可配超时/重试

- **Decision**: `SceneMetaConfig.max_dm_calls`（引擎到顶后跳过裁决）由 DMOptions
  透出，默认 50；`LiteLLMDMProvider(timeout=30, max_retries=2)` 常量配置。
- **Rationale**: 宪章 VI 成本边界；引擎内建帽子比外挂计数可靠（在裁决入口
  之前拦截）。

## R7: 故障降级——引擎内建，本特性只配置不实现

- **Decision**: 不新增降级代码。引擎 resolve_dm 已有完整路径：效果非法 →
  error_feedback 回注重试；调用失败 → 记录 `dm_call(failed=True)` +
  `emit_fallback_narrative` 兜底叙事，run 不中断。
- **Rationale**: 满足 FR-005 的全部要求已在引擎侧存在；重复实现只会分叉行为。
- **证据**: `engine/dm_resolver.py` validate_dm_effects / resolve_dm 全文。
