# Feature Specification: 初始化与使用技能分发

**Feature Branch**: `022-init-skills`

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "为 narrative-sim 增加统一初始化与使用技能分发。新增 narrative init / NarrativeSim.exe init：创建用户 HOME 的 data/logs/run/models/cache/skills 等目录，按模板首次生成 config.ini、.env 和 skills/narrative-sim/SKILL.md，输出路径与 created/existing 状态，已有文件一律不覆盖；不启动服务、不下载模型、不修改数据库。发行包携带 .env.example 与技能模板。技能应指导 Agent 使用本项目的 CLI、MCP、调研主库/项目库/古籍库边界、典型离线及真实工作流和安全约束。开发与冻结行为一致，原有 start 自动最小初始化保持兼容。不包含 GUI、模型下载或团队脚手架。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 一条命令完成首次配置 (Priority: P1)

作为新用户，我希望执行初始化命令即可得到完整的目录、配置模板和使用说明，不必手工猜测文件位置。

**Why this priority**: 初始化是独立应用首次使用与故障排查的共同入口。

**Independent Test**: 在全新临时 HOME 执行 init，检查目录、配置模板、技能及结构化结果；不启动任何服务。

**Acceptance Scenarios**:

1. **Given** 全新用户目录， **When** 执行 init， **Then** 创建所需目录、配置模板和项目使用技能，并返回各文件位置及 created 状态。
2. **Given** 缺少真实密钥或模型， **When** 执行 init， **Then** 初始化仍成功，不下载、不启动、不调用模型。

---

### User Story 2 - 升级时不覆盖用户内容 (Priority: P2)

作为已有配置的用户，我希望重复初始化或升级程序时保留自己的配置和技能修改，避免被模板覆盖。

**Why this priority**: 用户配置和技能可能经过定制，安全升级必须优先于模板更新。

**Independent Test**: 修改初始化后的 `.env`、config.ini 和技能，重复执行 init 并替换程序目录，检查内容不变且状态为 existing。

**Acceptance Scenarios**:

1. **Given** 已存在用户文件， **When** 重复 init， **Then** 不覆盖任何已有文件，缺失项单独补齐。
2. **Given** 用户文件不可写， **When** 执行 init， **Then** 返回失败和具体路径，不把部分完成报告为整体成功。

---

### User Story 3 - Agent 获得一致的项目使用技能 (Priority: P3)

作为 Agent 使用者，我希望发行版自带可直接使用的项目技能，使 Agent 能正确调用 CLI/MCP 并遵守数据库和安全边界。

**Why this priority**: 技能是项目能力被发现和正确使用的主要说明入口。

**Independent Test**: 检查发行包中的技能模板及初始化后的技能内容，验证包含命令入口、MCP、三库分工、典型工作流和密钥保护。

**Acceptance Scenarios**:

1. **Given** 开发或冻结发行环境， **When** 初始化完成， **Then** 用户技能目录中存在内容一致的技能文件。
2. **Given** Agent 阅读技能， **When** 执行调研或仿真， **Then** 能依据技能找到正确命令、数据位置和停止服务方式。

### Edge Cases

- 部分目录或文件已存在时只补缺失项，不覆盖或清空。
- HOME 包含中文、空格或长路径时模板复制正常。
- `.env` 模板不含真实密钥，初始化不得读取或回显现有密钥。
- 技能模板缺失或发行资源损坏时明确失败，不生成空技能。
- start 的最小自动初始化与显式 init 共用同一实现，行为不得分叉。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 开发与冻结入口 MUST 提供相同的 init 命令及结构化结果。
- **FR-002**: init MUST 创建数据、日志、运行状态、模型、缓存和技能目录，并输出用户 HOME 与文件状态。
- **FR-003**: init MUST 按模板首次生成 config.ini、`.env` 和 `skills/narrative-sim/SKILL.md`；已有文件 MUST 标记 existing 且不得覆盖。
- **FR-004**: 初始化 MUST NOT 启动服务、下载模型、调用 LLM、修改业务数据库或输出真实密钥。
- **FR-005**: 发行包 MUST 携带 `.env.example` 与技能模板，冻结 init MUST 能从只读程序资源复制它们。
- **FR-006**: 技能 MUST 说明 CLI、MCP、三库职责、离线/真实工作流、服务启停、密钥保护与数据来源约束。
- **FR-007**: start 的自动初始化与显式 init MUST 共用同一实现，开发模式现有默认路径保持兼容。
- **FR-008**: 初始化失败 MUST 返回非零并指出具体路径或缺失资源，不得输出虚假成功。
- **FR-009**: README 与开发手册 MUST 给出初始化、技能位置和升级保留规则。
- **FR-010**: 全部现有离线测试、MCP 契约、冻结验收和 M1 MUST 保持通过。

### Key Entities

- **初始化结果**: HOME、文件路径及 created/existing 状态。
- **配置模板**: 不含密钥的默认环境模板和运行配置。
- **项目使用技能**: 面向 Agent 的 CLI/MCP 与数据边界说明模板。
- **用户目录**: 全部可写配置、数据、日志、缓存和技能的统一根目录。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 全新 HOME 一次 init 即创建全部约定目录和 3 个模板文件，结果中的路径与 created 状态准确率 100%。
- **SC-002**: 修改全部已有文件后重复 init，文件内容保持不变，已有项均报告 existing，缺失项单独补齐。
- **SC-003**: 开发与冻结 init 生成的技能内容一致，发行包与初始化结果均通过技能内容检查。
- **SC-004**: init 全过程服务启动数、模型下载数和业务数据库写入数均为 0。
- **SC-005**: 全部现有离线测试、冻结回归、M1 与构建验收通过。

## Assumptions

- 技能使用项目内的 `resources/skills/narrative-sim/SKILL.md` 作为只读模板，初始化复制到用户 HOME。
- 已有用户技能不自动更新；未来模板升级需另行设计显式迁移，不在本特性覆盖。
- 不包含 GUI、模型下载、自动更新、团队脚手架或全局 Agent 配置修改。
