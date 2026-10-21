# Research: 创作队对接接口

**Date**: 2026-10-21 | **Feature**: 011-creation-interface

无 NEEDS CLARIFICATION 遗留；以下为关键决策（证据为本地源码实读）。

## R1: 修订存储——快照式叠加层 + 指针列，非 diff 链

- **Decision**: `asset_revisions` 每版存**完整 payload 快照**；
  `assets.current_revision` 为当前指针；`assets.payload` 恒等于指针版快照
  （读路径零改动，get_asset/list_assets 不用动）。
- **Rationale**: diff 链回滚要逐层重放，快照式回滚是一次指针移动 + 回填；
  资产量级（百级 × KB 级 JSON）下存储冗余可忽略；读路径零改动 = 既有
  141 项测试零回归风险。
- **Alternatives considered**: 纯 diff 链（回滚重放复杂、取历史版需重放，
  否决）；事件溯源（对百级资产是杀鸡用牛刀，否决）。

## R2: revision 0 由 put_asset 自动建立；内部 REPLACE 自动升版

- **Decision**: `put_asset` 首次插入时自动写 revision 0（author = 资产
  provenance.retriever 或 "system"）；对已有修订记录的资产做 REPLACE 且
  payload 有变化时自动追加一版（author="system:put_asset"）。
- **Rationale**: 调研管线（004/009）是资产的第一写入者，revision 0 = 调研
  原版由此免费获得；内部 REPLACE（脚本重置演示资产等）若静默改内容，
  修订层就有暗道——自动升版把它照亮，防污染不留后门（FR-009）。
- **证据**: `store.py:48-60` put_asset 为 INSERT OR REPLACE；
  `brief.py`/`research.py` 去重命中不重写 payload，正常调研流不会触发
  自动升版。

## R3: 冲突警告做成"使用留痕"，不做语义矛盾判断

- **Decision**: revise_asset 响应携带 `impacted`：引用过该资产的
  world/run 列表及各自冻结版号（从 worlds.config 的 revisions pin 反查）。
  不尝试 NLP 级"人设与剧情矛盾"判断。
- **Rationale**: FR-010 要求"警告 + 留痕 + 不拦截"。语义矛盾判断（如
  "已暴露改回潜伏中"）需要理解事件内容，误报率高且无权威答案；使用
  留痕是确定性的、可测试的，且信息上等价——创作队看到"这卡已被 run X
  用过"自然知道要核对什么。
- **Alternatives considered**: LLM 判矛盾（引入成本与不确定性，且裁决权
  不该在系统手里，否决）。

## R4: 世界 config 钉版号（pin），run 按 pin 取卡

- **Decision**: create_world 冻结的 config 增加 `revisions: {asset_id: rev}`；
  run_simulation/重拍按 pin 经 `store.get_asset_at_revision` 取卡。
  旧库世界 config 无 revisions 键 → 按当前版取卡（向后兼容）。
- **Rationale**: spec 要求"任一 run 的角色卡版本可复现可追溯"。只记版号 +
  修订表有完整快照 = 可复现；不必把整个场景 config 冻结进库（冗余且
  world.py 每 run 重建 config 是 006 既定架构）。
- **证据**: `mcp_server.py:72-75` 现状 config 只存 character_ids/location_id；
  `run_world` 每 run 重新 build_scene_config。

## R5: 重拍 = 重钉版 + 新 run，不加新机制

- **Decision**: `reshoot(world_id, new_run_id, use_latest=False, ...)`：
  use_latest=False 用世界已冻结 pin 原样重跑；True 则把 pin 重钉到各资产
  当前版（更新 worlds.config）再跑。run_id 全新 → 事件编号经
  max_event_no() 全局连续（006 机制），两版天然并存可 diff。
- **Rationale**: 重拍的所有构件（冻结 config、resume、全局编号）都已存在，
  reshoot 只是把它们组合成一个语义明确的工具。revision_pin 显式 dict 参数
  不单独做——use_latest + revise_asset 已覆盖该场景（先修订再重拍）。
- **Alternatives considered**: 显式 pin dict 参数（与 use_latest 功能重叠，
  多一条少用的路径，否决）。

## R6: 移交包——目录 + manifest，sha256 做完整性锚

- **Decision**: `handoff/<world_id>/`：manifest.json（格式版本、world/run 标识、
  每项文件的计数 + sha256 + 修订版号锚点、密级说明）+ assets/*.json +
  events.jsonl + world.json + dm_calls.json + materials/<asset_id>.md +
  sources.md。manifest 自描述 = 外部 agent 只读 manifest 即可定位全部内容。
- **Rationale**: JSONL/MD 是创作技能链（ai-manju-scriptwriter 等）直接可
  消费的格式；sha256 给"移交后是否被改过"一个可验锚点；materials 转 md
  是因为原料原文是给人/LLM 读的，不是给程序 join 的。
- **Edge**: out_dir 已存在默认拒绝（HandoffExists），overwrite=True 才覆盖
  （spec Edge Case）。

## R7: MCP 错误词汇表沿用 007 口径

- **Decision**: 新错误类型 AssetNotFound / RunNotFound / WorldNotFound /
  RevisionNotFound / RevisionConflict / HandoffExists，统一
  `ToolError("{类型}: {原因}")`。
- **Rationale**: 007 已确立此口径且测试覆盖（SC-004 grep 门禁）；创作 agent
  解析错误时一套词汇表走天下。
