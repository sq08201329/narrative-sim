# Phase 0 Research: 故事时间树

## 抽取与重试

- **Decision**: `story_tree.parse_story(text, chat_json_fn=None)` 用 `llm.chat_json` 做结构化抽取，结果经 `story_tree.schema.json` 校验；失败重试一次，仍失败则抛错不入库。
- **Rationale**: 复用既有 LLM 接缝与 `brief.generate_brief` 的「漂移重试一次」模式；schema 是唯一契约（宪章 I）。
- **Alternatives considered**: 正则/规则抽取（中文叙述鲁棒性差）；跳过 schema 直接入库（违反宪章 I）。

## source_span 自查

- **Decision**: 机器逐字比对 `text[start:end] == quote`；不等即自查失败。偏移越界、quote 为空同样失败。
- **Rationale**: 客观可判定，原文即证据，不需要人工判断，满足用户「自查一遍」要求。
- **Alternatives considered**: 只检查偏移不比对内容（假阳性高）；用模糊相似度（不可复现）。

## node_id 与 M1 兼容

- **Decision**: `event.schema.json` 增加**可选** `node_id`（pattern `^n[0-9]{4,}$`），仅树驱动 run 写入；M1 与既有 run 不写。
- **Rationale**: M1 事件没有节点，必填会破坏离线确定性基线（宪章 IV）；可选字段向后兼容。
- **Alternatives considered**: 设为必填并给 M1 造节点（污染契约语义）；另建事件表（多写入口，违反 III）。

## 世界与 tick 映射

- **Decision**: 每个不同空间节点建一个 world（`world_id = {base}__{node_id}`），沿用「一世界一 location」语义；run 阶段对该世界内节点按 tick 均分，tick 0 归首节点。
- **Rationale**: 无需改动 `world.py` 的 location 语义，避免单世界多 location 的大改与易错。
- **Alternatives considered**: 单世界多 location（需重写场景配置和事件 location，风险高）。

## 导出排序

- **Decision**: `store.export_events` 解析 payload 后在 Python 侧按 `(node_id, tick, seq)` 排序；不新增列、不迁移旧数据。
- **Rationale**: 无 `node_id` 的 M1 事件等价于按 `(tick, seq)`，零回归；避免 DDL `ALTER` 破坏既有数据（宪章 III）。
- **Alternatives considered**: events 表加 `node_id` 列并迁移（违反 DDL 幂等/不破坏既有数据）。

## 调研清单映射

- **Decision**: 实体去重后映射为 brief items（`character` → category `character`；`scene`/`prop` → category `world`），调用 `brief.execute_brief` 复用四层漏斗；用 ledger 的 `asset_id` 回填 `entity_assets` 映射。
- **Rationale**: 不重写调研去重逻辑，不绕过缓存/复用/合并/attach（FR-010）。
- **Alternatives considered**: 直接调 `research_asset`（丢掉四层漏斗，重复调研）。

所有 NEEDS CLARIFICATION 已解决。
