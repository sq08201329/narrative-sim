# Changelog

本文件只记录**用户可感知**的变化（新增能力、行为变化、重要修复）。

版本约定：本仓库此前从未打 tag。本版为**首个带 tag 的版本**（`v0.2.0`），
接口仍可能变化（0.x 语义，不承诺向后兼容）。

## [Unreleased]

> `v0.2.0` tag 指向发版提交，不后移；以下变化为 tag 之后的增量，尚未发版。

### 参考图

- 图生图参数：`generate_reference_image` 新增 `subject_reference`（本地 JPG/PNG 或 data URL，单张、≤10MB，只锁主体长相）与 `seed`（同参可复现）；返回值带 `seed` / `used_reference` 便于记台账。不传新参时请求与行为与 0.2.0 逐键一致；参考图非法（缺失/格式不对/超 10MB）在发请求前报错、零计费。

## [0.2.0] - 2026-10-23

> 发布说明：本版为首个带 tag 的版本；接口仍可能变化（0.x 语义，不承诺向后兼容）。

> **内部版本**：本版仅限内部使用，**外部不可安装**。依赖 `worldseed[dm]` 来自本机
> path 且带本地编码补丁（见 `docs/worldseed-local-patch/`）；PyPI 上的 `worldseed`
> 是另一个发行版（0.0.1，只有 `gui` extra），不能替代。
>
> 干净环境验证（2026-10-23）：`uv lock --check` 通过（309 包），`uv sync --frozen`
> 成功（52.4s，1.4 GB venv），离线测试 **225 passed / 1 deselected**。
> **除 worldseed 外的 308 个依赖均可从公开源装齐**——这正是本版定为「内部版」的原因。

### 调研与素材

- 新增调研管线：查询词 → 史料检索（gptr-mcp / DeepSeek 检索腿）→ 质量校验 → 资产卡入库（`import`）。
- 新增立项调研（`research_brief`）：一句题材拆成 world / character / lore 三类清单，逐条执行；带四层去重漏斗（查询级预判 / 成卡后比对 / 清单内去重 / 原料挂靠）。
- 新增原料（lore）入库：`research_material` 把检索结果作为史料原料挂到指定资产，不资产化。
- 新增语义去重：重复主题命中已有资产时复用、不重复造卡；嵌入服务缺席时降级为名称精确匹配并告警。

### 世界与仿真

- 新增世界搭建（`create_world`）：按资产版号钉住角色与场景。
- 新增引擎驱动的仿真（`run_simulation`）：tinytroupe 真后端 / mock 离线后端；每回合快照可续跑，事件编号全局连续。
- 新增重拍（`reshoot`）：按冻结版号重跑，或 `use_latest` 把版号重钉到最新版；两版事件并存可 diff。
- 新增幕间记忆：从上一幕事件生成角色记忆，下一幕注入，避免见面重新自我介绍。

### 裁决（DM）

- 新增真实裁决：角色的 `action` 类动作由模型判定效果（`say` 直接放行）；每次裁决落审计台账（`list_dm_calls`）。
- 裁决模型默认 `deepseek-chat`（思考模型不支持裁决所需的 tool_choice）。

### 移交

- 新增移交包导出（`export_handoff`）：manifest（sha256/计数/版号锚点/密级）、资产、事件流、世界快照、裁决台账、调研原料、溯源汇总。
- 参考图默认不带：自产图为内部草稿，创作部门以 `visual_prompt` 为准重做；`include_images=True` 才复制。

### 资产版本与参考图

- 新增资产修订版本化：`revise_asset` 升版（乐观锁 `base_revision`）、`rollback_asset` 回指历史版；历史不删。
- 新增参考图生成：按资产 `visual_prompt` 出图（MiniMax），图片落盘 + 出图台账。
- **行为变化**：出图不再顶资产修订号，`reference_images` 改为从出图台账派生（此前每出一张图就会升一版，历史修订保留）。

### 双库与搬运

- 库结构拆分为「调研主库 `data/library.db` + 项目工作库 `data/projects/linan.db`」：调研只写主库，仿真/移交只用项目库。
- 新增资产搬运（`asset_port` export / import / verify）：保号、幂等、冲突不覆盖；手写资产（`provenance=manual`）默认拒导；跨库比对用内容哈希，忽略仅在出图台账里体现的图片差异。

### 运维

- 新增一键起停技术栈 `scripts/start_stack.ps1`：固定顺序（嵌入服务 → 调研服务 → 叙事服务）、健康检查门槛、幂等、自动带项目库。
- 新增资产修订差异与素材判定台账：`data/asset_notes/<asset_id>.md` 与库级说明。
- 新增 `.gitignore` / `.gitattributes`：库文件、备份、日志、参考图不入库；仓库内统一 LF（Windows 脚本 CRLF）。

### 质量与修复

- 修仿真台词语言漂移：每回合提示硬约束「只用中文」，不再漂成日语/英文。
- 修单测读取项目 `.env` 导致的环境泄漏：离线测试默认不读 `.env`（`real` 标记的在线用例除外）。
- 修跨库导入误拒：项目库因出图修订号更高时，内容一致即可导入（`identical_content`），不再误报「目标库领先」。
- 修 WorldSeed 引擎续跑：同一 `run_id` 可在中断后继续追加事件（不再撞「run_id 已存在」）。

### 已知限制

见 [KNOWN-LIMITATIONS.md](KNOWN-LIMITATIONS.md)。
