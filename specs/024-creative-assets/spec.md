# Feature Specification: 创作资产管理技能（Creative Assets）

**Feature Branch**: `024-creative-assets`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "在技能里教创作团队怎么根据故事时间树管理工作目录：每个节点目录怎么取名、资产放不放节点目录、节点新增资产怎么管理。技能主体写技能文件，文档里放指针，移交包另带一份。技能按资产管理命名（creative-assets），创建目录只是其中一节。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 创作 Agent 获得可执行的资产管理技能 (Priority: P1)

作为创作团队的 Agent 使用者，我希望有一个独立技能，告诉我拿到时间树后怎么组织工作目录、怎么管理资产，并且不会被误当成操作仿真工具的技能。

**Why this priority**: 这是本特性的核心交付；没有技能，创作团队就没有统一约定。

**Independent Test**: 检查 `creative-assets/SKILL.md` 存在、frontmatter 的 name/description 正确、内容覆盖资产管理的六节、且与 `narrative-sim` 技能触发边界清晰。

**Acceptance Scenarios**:

1. **Given** 创作团队的 Agent 面对素材整理任务，**When** Agent 加载 `creative-assets` 技能，**Then** 技能给出资产来源、编号、归属、物理布局、改版、移交六节完整规范。
2. **Given** 用户面对仿真工具操作任务（调研/建世界/跑仿真），**When** Agent 选择技能，**Then** 只加载 `narrative-sim` 技能，不误加载 `creative-assets`。

---

### User Story 2 - init 把技能分发到创作团队环境 (Priority: P1)

作为创作团队成员，我希望执行一次 init 就能在自己的 HOME 里拿到这份技能，开发和冻结版行为一致，且我改过的技能不会被升级覆盖。

**Why this priority**: 技能只有分发到使用者的环境才会被 Agent 发现；沿用 022 的不覆盖规则保护用户修改。

**Independent Test**: 在临时 HOME 执行 init，检查 `<HOME>/skills/creative-assets/SKILL.md` 被创建；修改后重复 init，内容不变且状态为 existing。

**Acceptance Scenarios**:

1. **Given** 全新用户目录，**When** 执行 init，**Then** 创建 `skills/creative-assets/SKILL.md`，内容与模板一致，状态 created。
2. **Given** 用户已修改技能，**When** 重复 init 或升级程序目录，**Then** 技能内容不变、状态 existing。
3. **Given** 冻结版 EXE，**When** 执行 init，**Then** 从只读资源复制同一模板到 HOME，内容与开发版一致。

---

### User Story 3 - 移交包自带工作目录规范 (Priority: P2)

作为拿到移交包的创作团队，我希望包里就有一份工作目录规范，不必先跑 init 或去翻项目文档。

**Why this priority**: 创作团队作为下游，实际交付物是移交包；规范随数据走才能被真正用到。

**Independent Test**: 执行一次 `export_handoff`，检查移交包根出现 `WORKDIR.md`，内容即工作目录规范，且被 manifest 的 items 记录 sha256。

**Acceptance Scenarios**:

1. **Given** 一个已建世界，**When** 导出移交包，**Then** 包内存在 `WORKDIR.md`，内容与 `creative-assets` 技能的工作目录规范同源。
2. **Given** 移交包已有 manifest，**When** 检查 items，**Then** `WORKDIR.md` 被记录且 sha256 与文件实算一致。
3. **Given** 不覆盖重复导出，**When** 第二次导出未加 overwrite，**Then** 按既有 HandoffExists 行为拒绝。

---

### User Story 4 - 人能快速了解约定并找到技能 (Priority: P2)

作为创作团队负责人，我希望在 README 和开发手册里能 30 秒看懂工作目录约定，并知道完整规范在哪个技能里。

**Why this priority**: 文档指针是「人读」入口，技能是「Agent 执行」入口，两者互补。

**Independent Test**: 检查 README 与开发手册各有创作工作目录小节，含目录树总览、三条铁律和技能指针。

**Acceptance Scenarios**:

1. **Given** README 与开发手册，**When** 阅读创作工作目录小节，**Then** 看到目录树总览、三条铁律（node_id 稳定键 / ord 唯一 / 资产只引用不复制）和指向 `creative-assets` 技能的说明。
2. **Given** 现有文档内容，**When** 加入新小节，**Then** 既有章节结构与内容不被破坏。

---

### Edge Cases

- `<HOME>/skills/creative-assets/` 已存在但缺 SKILL.md：只补缺失文件，不覆盖已有内容。
- 冻结资源中技能模板缺失：init 明确失败并指出路径，不生成空技能。
- 移交包目录已存在：沿用既有 HandoffExists，不静默覆盖 WORKDIR.md。
- 创作团队尚未使用时间树：技能说明「无 node_id 时的退化工序」，不强制要求时间树存在。
- 手工新建资产无调研 provenance：按规范分配 asset_id 并标注来源为手工，不伪造 provenance。
- 同一资产在多个节点出现：只在 node.json 加引用，不改 first_seen_node。
- `text_time` 含非法文件名字符或超长：按规范替换为安全短名，node_id 保持不变。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 新增 `skills/creative-assets/SKILL.md`（仓库可编辑副本）与 `resources/skills/creative-assets/SKILL.md`（只读模板），两者字节一致 — US1
- **FR-002**: 技能 frontmatter 的 `name` MUST 为 `creative-assets`，`description` MUST 明确「创作团队基于时间树管理素材资产与工作目录」，并与 `narrative-sim` 技能的「调研与仿真工具操作」划清触发边界 — US1
- **FR-003**: 技能正文 MUST 覆盖六节：资产来源、资产编号、归属（first_seen_node）、物理布局（全局资产区 + 节点目录只放 node.json 引用 + 派生物目录）、改版与重拍、移交；工作目录/命名规则作为「物理布局」一节的子内容 — US1
- **FR-004**: 技能 MUST 写明三条铁律（node_id 为稳定键、ord 全项目唯一、资产本体只引用不复制）与节点目录命名规则 `N{ord:04d}_{text_time或顺位}_{地点/事件短名}` — US1
- **FR-005**: `orchestrator/init_app.py` 的 TEMPLATES MUST 增加 `skills/creative-assets/SKILL.md`，复制已有文件不覆盖（022 规则） — US2
- **FR-006**: 冻结包 MUST 经既有 `resources/` 打包携带新技能模板，init 从只读资源复制，开发与冻结内容一致 — US2
- **FR-007**: `orchestrator/handoff.py` 的 `export_handoff` MUST 在移交包根写 `WORKDIR.md`，内容为工作目录规范，且经 `_write` 计入 manifest items（sha256 自描述）；MUST NOT 改变既有 counts 口径 — US3
- **FR-008**: WORKDIR.md 内容 MUST 与技能的「物理布局 + 归属」两节同源，避免规范分叉 — US3
- **FR-009**: README 与 `mydocs/叙事仿真系统开发手册.md` MUST 各加创作工作目录小节，含目录树总览、三条铁律与技能指针 — US4
- **FR-010**: 本特性 MUST NOT 修改任何 schema、数据库 DDL 或存储入口；WORKDIR.md 是移交包内的静态文档，不引入新存储域（宪章 I/III） — 全局
- **FR-011**: MCP `export_handoff` 工具行为与参数 MUST 不变；M1 与现有离线测试 MUST 不回归 — 全局

### Key Entities

- **creative-assets 技能**: 面向创作团队 Agent 的资产管理执行手册，六节正文 + 三条铁律。
- **技能模板**: `resources/skills/creative-assets/SKILL.md`，init 与冻结复制的唯一来源。
- **工作目录规范**: 全局资产区 / 节点目录 / 派生物目录的布局与命名约定；技能的物理布局一节。
- **WORKDIR.md**: 移交包内的规范副本，随数据交付给下游。
- **init 结果**: 新增技能文件的 created/existing 状态。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 全新 HOME 执行 init 后，`<HOME>/skills/creative-assets/SKILL.md` 创建成功且与模板字节一致；修改后重复 init 内容不变、状态 existing。
- **SC-002**: 开发与冻结 init 生成的技能内容一致，发行包含技能模板且无真实数据。
- **SC-003**: `export_handoff` 产出的移交包含 `WORKDIR.md`，manifest 中该文件的 sha256 与实算一致，既有 counts 与 sha256 自描述断言不回归。
- **SC-004**: 技能内容覆盖全部六节与三条铁律，frontmatter name/description 与 `narrative-sim` 技能无触发冲突。
- **SC-005**: M1 回归、现有离线测试、契约守卫与 MCP 测试全部通过。

## Assumptions

- 本特性是文档/模板/薄代码扩展，不引入新依赖、不调用 LLM、不读写业务数据库（宪章 V/VI 自然满足）。
- 技能引用的 `node_id` / timeline 命令来自 023 特性；本特性在 024 分支独立落地，技能以「无 node_id 时的退化工序」兼容 023 未合并的情形，不依赖 023 代码即可成立。
- `first_seen_node` 是创作工作目录的约定，写入技能的资产管理规范，不进入项目 `asset.schema.json`。
- 三处技能落地沿用 022 已建立的分发机制（仓库副本 + 只读资源模板 + init 复制到 HOME），不修改全局 Agent 配置。
- WORKDIR.md 是静态规范文档，放 `resources/skills/creative-assets/WORKDIR.md` 作为同源文本；技能「物理布局/归属」两节与其保持一致。
- 一个特性一个分支 `024-creative-assets`，遵循 spec → plan → tasks → implement → analyze → converge 全链条。
