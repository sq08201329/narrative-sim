# Feature Specification: 创作队对接接口（读取 + 修订版本化 + 重拍 + 移交包）

**Feature Branch**: `011-creation-interface`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: "创作团队是 agent team：盘点并补齐接口——读存量、资产修订版本化（防污染/回滚/重拍）、素材移交包。"

## 背景与动机

本系统的下游消费者是一个 agent 创作团队（写剧本、画分镜、做视频）。现有 MCP
接口（007）只有"发起"能力（调研、建世界、跑仿真），**没有"读取"能力**——
创作 agent 问不出库里有什么、角色卡长什么样、上一幕发生了什么。同时创作过程
必然修改人设与设定，这些修改需要可保存、可回滚、可重拍地接力到下一幕，且
不得污染调研原版与已发生剧情。

设计原则（讨论已拍板）：**调研和仿真是历史，创作修订是层，幕的 config 是锚。**
污染靠冻结面防，回滚靠指针，重拍靠锚 + 新 run。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 创作 agent 读取全部存量 (Priority: P1)

创作 agent 经 MCP 接口完成完整读路径：列出库里资产 → 读某个角色的完整卡
（含 persona_spec、外观、溯源、当前修订版号）→ 读该角色的调研原料原文 →
读某次 run 的事件流 → 读世界快照 → 读裁决台账。全程不经文件中转、不直连
数据库。

**Why this priority**: 读是一切的起点——没有读接口，修订、移交、重拍都无从
谈起；这也是 agent team 接入的最低可用集（MVP）。

**Independent Test**: 用预置演示库，经 MCP 客户端依次调全部读工具，返回值
与库内数据一致，零文件落地。

**Acceptance Scenarios**:

1. **Given** 库内有资产与原料，**When** agent 调 list_assets / get_asset /
   get_materials，**Then** 返回结构化数据（含 persona_spec 全字段、provenance、
   当前修订版号），与库内一致。
2. **Given** 某 run 已完成，**When** agent 调 get_events / get_world_state /
   list_dm_calls，**Then** 直接返回事件列表、快照、裁决台账，无需读文件。
3. **Given** 查询不存在的资产/run/世界，**When** 调对应读工具，**Then** 返回
   结构化错误（明确的"不存在"语义），不抛栈、不返回空串。
4. **Given** 角色卡含 secret 字段，**When** 创作 agent 读资产，**Then** secret
   可见且响应中显式标注其密级（创作可见、仿真角色不可见的分层语义不丢失）。

---

### User Story 2 - 资产修订版本化与回滚 (Priority: P2)

创作 agent 修改角色卡（如调整性格、加伏笔设定），系统存为新修订版：调研原版
（revision 0）永远保留，修订逐层叠加并记录作者与理由。改错了可一键回滚到
任意历史版本。修订永不写入原料表、不修改已发生事件、不改动已冻结的世界
config。

**Why this priority**: 这是"创作修改怎么保存"的答案，是创作队真正动工的前提；
依赖 P1 的读接口来验证修订结果。

**Independent Test**: 修订 → 读回验证新版本 → 回滚 → 读回验证旧版本 →
检查原料表/事件/世界 config 三处零变化。

**Acceptance Scenarios**:

1. **Given** 一个调研生成的资产，**When** agent 调 revise_asset 提交修改
   （patch + 理由 + 作者），**Then** 资产当前版更新为新修订，历史含
   revision 0（调研原版）与新版本，各自完整可取。
2. **Given** 某资产有多次修订，**When** agent 调 rollback_asset 指定目标版，
   **Then** 当前版指针回到该版，修订历史不删，基于被撤回版本建的世界/run
   被标记 stale 但数据不变。
3. **Given** 一次修订与已发生事件矛盾（如把"已暴露"改回"潜伏中"），**When**
   提交修订，**Then** 修订成功但响应带冲突警告（创作自由不强制拦，必须留痕）。
4. **Given** 任意修订与回滚操作后，**When** 检查原料表、事件表、既有世界
   config，**Then** 三者与被修订前逐字节一致（污染防线）。
5. **Given** 回滚目标版号不存在，**When** 调 rollback_asset，**Then** 返回
   结构化错误，当前版不变。

---

### User Story 3 - 素材移交包 (Priority: P2)

创作 agent 一个调用拿到某世界（或某 run）的完整移交目录：manifest（清单 +
版本 + 修订版号锚点）+ 资产全字段 + 事件流 + 世界快照（含 secret，显式密级
标注）+ 裁决台账 + 调研原料导出 + 溯源汇总。目录自描述，外部 agent 仅凭
manifest 即可解析全部内容。

**Why this priority**: 这是"素材移交给谁"的最终答案——M6 的落地。与 US2 同级：
移交包的内容锚定修订版号，逻辑上依赖 US2 的版本概念，但两者可分别交付。

**Independent Test**: 对演示库导出移交包，仅凭 manifest 解析出全部资产/事件/
原料，字段与库内一致；空库导出明确空结构不报错。

**Acceptance Scenarios**:

1. **Given** 某世界有资产、事件、裁决与原料，**When** agent 调
   export_handoff，**Then** 产出目录含 manifest + 全部内容文件，manifest
   记录每项的版号/数量/哈希或等价校验信息。
2. **Given** 移交包中的角色卡，**When** 创作 agent 读取，**Then** 包含 secret
   且带密级标注（区别于仿真可见信息）。
3. **Given** 空世界（无事件无裁决），**When** 导出移交包，**Then** 目录结构
   完整、对应项为空集合并显式标注，不报错。

---

### User Story 4 - 重拍 (Priority: P3)

创作队对某幕不满意时发起重拍：原样重拍（同 config 换裁决/后端新跑一个 run）
或修订重拍（pin 指定修订版重建世界，从上一幕快照接力）。两版 run 并存，
事件编号全局连续不冲突，可分别导出对照。

**Why this priority**: 重拍是质量打磨手段，依赖 US2 的修订版号概念；核心链路
（读/修订/移交）没有它也能跑通，故 P3。

**Independent Test**: 对同一世界原样重拍一次、修订重拍一次，三个 run 并存，
事件编号无冲突，各自可导出。

**Acceptance Scenarios**:

1. **Given** 某世界已有一版 run，**When** agent 调 reshoot 原样重拍，
   **Then** 产出新 run，世界 config 不变，事件编号全局连续。
2. **Given** 角色卡已修订到新版本，**When** agent 调 reshoot 并 pin 修订版，
   **Then** 新 run 的世界 config 记录所用修订版号，角色行为依据新版卡。
3. **Given** 两版 run 并存，**When** 分别导出事件，**Then** 两版完整独立，
   event_id 零冲突。

---

### Edge Cases

- 修订 patch 为空或与当前版完全相同：接受并存为新版本（留痕重于判重），
  或明确拒绝——实现时取其一并在契约中写死。
- 并发修订同一资产：后到者基于的版号已过时，返回冲突错误要求重读。
- 移交包导出目标目录已存在：覆盖需显式确认参数，默认拒绝。
- 重拍的世界无上一幕快照（首幕）：修订重拍等同新建，不报错。
- 读接口在库未初始化/表缺失（旧库无新表）：返回结构化错误或空集，不抛栈。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: MCP 新增读工具 list_assets(type?)、get_asset(asset_id)，返回
  资产全字段（含 persona_spec、appearance、provenance、当前修订版号）。
- **FR-002**: MCP 新增读工具 get_materials(asset_id)、search_materials
  (keyword)，返回调研原料（query/retriever/context/created_at）。
- **FR-003**: MCP 新增读工具 get_events(run_id)，直接返回事件列表（与
  export_events 文件口径一致）。
- **FR-004**: MCP 新增读工具 get_world_state(world_id)，返回最新快照
  （tick + 状态）。
- **FR-005**: MCP 新增读工具 list_dm_calls(run_id)，返回裁决台账。
- **FR-006**: 系统 MUST 提供资产修订版本化：revise_asset(asset_id, patch,
  reason, author) 存新修订版；revision 0 为调研原版，不可改不可删；
  每版记录作者、理由、时间、完整内容快照。
- **FR-007**: 系统 MUST 提供 rollback_asset(asset_id, to_revision)：移动当前
  版指针、保留全部历史；基于被撤回版本的世界/run 标记 stale 且不改动其
  数据；目标版不存在时返回结构化错误。
- **FR-008**: 建世界时冻结的 config MUST 记录所用每个资产的修订版号，
  使任一 run 的角色卡版本可复现、可追溯。
- **FR-009**: 修订/回滚 MUST NOT 写原料表、改事件表、改已冻结的世界
  config（污染防线，违例即宪章级事故）。
- **FR-010**: 修订与已发生事件矛盾时 MUST 在响应中返回冲突警告，但不强制
  拦截（创作自由 + 留痕）。
- **FR-011**: MCP 新增 export_handoff(world_id, out_dir?, run_id?)：产出
  自描述移交目录（manifest + assets + events + world 快照 + dm_calls +
  materials + sources），角色 secret 带密级标注；目录已存在时默认拒绝
  覆盖。
- **FR-012**: MCP 新增 reshoot(world_id, revision_pin?, new_run_id)：原样
  或指定修订版重拍，产出新 run，事件编号全局连续。
- **FR-013**: 既有 run_simulation 工具 MUST 增加 dm 开关参数（010 能力进
  MCP）；缺省不启用，向后兼容。
- **FR-014**: MCP 新增 research_brief(theme) 工具（009 立项能力进 MCP）。
- **FR-015**: 全部新工具为 store/orchestrator 既有能力的薄封装（宪章 II/III）；
  离线测试零外部调用，既有测试无回归。
- **FR-016**: 所有读工具对"不存在"输入 MUST 返回结构化错误（含缺失对象
  标识），不抛栈、不静默返回空。

### Key Entities

- **AssetRevision（资产修订版）**: revision 号、asset_id、patch、完整内容快照、
  author、reason、created_at；revision 0 = 调研原版。
- **RevisionPin（版号锚点）**: 世界 config 中每个资产 → 修订版号的映射，
  建世界时冻结。
- **HandoffManifest（移交清单）**: 版本、世界/run 标识、内容项列表（每项
  类型/数量/版号锚点）、密级说明、生成时间。
- **移交目录**: manifest.json + assets/ + events.jsonl + world.json +
  dm_calls.json + materials/ + sources.md。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 创作 agent 经 MCP 完成"列资产→读卡→读原料→读事件→读快照→
  读台账"全读路径，零文件中转、零数据库直连，每步返回结构化数据。
- **SC-002**: 修订→回滚→再修订全程留痕；revision 0（调研原版）在任意操作
  序列后可 100% 恢复；三冻结面任意修订后逐字节不变（自动化断言）。
- **SC-003**: 重拍两版 run 并存，event_id 零冲突，各自可完整导出。
- **SC-004**: 移交包仅凭 manifest 可被外部程序完整解析（字段与库内一致率
  100%）；空世界导出成功率 100%。
- **SC-005**: 离线测试全绿零外部调用；既有 141 项无回归；新工具全部为
  薄封装（单工具新增逻辑行数可审）。

## Assumptions

- 创作 agent team 经 MCP（streamable-http）接入，与 007 同一服务实例；
  鉴权/多租户不在本期范围（本机可信环境）。
- 修订 patch 的格式（整体替换 vs JSON merge patch）属实现细节，plan 阶段定；
  契约要求写死其一。
- 移交包格式以 JSON/Markdown 为主，不含二进制；参考图（仍为空）留扩展位。
- 幕间记忆传递（上幕摘要注入下幕角色初始记忆）是相关但独立的能力，不在
  本期范围（待办池保留）。
- 并发控制采用"读取时记版号、提交时校验"的乐观锁口径；本机单服务实例
  下真并发罕见。
