# Feature Specification: 故事时间树（Story Timeline Tree）

**Feature Branch**: `023-story-tree`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "拿到一个完整的纯文本故事后，按时间线列出空间、人、事、物，形成一颗时间树；这棵树只是整理故事时间线的事实索引，不属于剧本创作。然后按照这棵树推进本项目的调研、世界、仿真与导出工作。抽取后不需要人工复核，由系统自查一遍。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 导入纯文本故事生成时间树 (Priority: P1)

作为叙事策划，我有一篇完整的纯文本故事，希望把它整理成按时间线排列的空间/人/事/物索引，并能回指原文，作为后续调研与仿真的依据。

**Why this priority**: 没有树就没有后续一切；本用例是 MVP，且独立于「驱动工作」即可交付价值——得到一份可回指原文的时间线索引。

**Independent Test**: 用一段含时间顺序、人物、地点、道具的纯文本执行 import，检查节点顺序、四类要素、source_span 回指与 ready 状态入库；不需要调研或仿真。

**Acceptance Scenarios**:

1. **Given** 一篇 UTF-8 纯文本故事，**When** 执行 `narrative timeline import T001 --story story.txt`，**Then** 系统自动完成自查，通过后生成 ready 状态的时间树，节点按叙述顺序排列，每节点带 source_span，命令输出自查报告并返回 0。
2. **Given** LLM 输出 JSON 漂移或契约校验失败，**When** 执行 import，**Then** 按既有模式重试一次；仍失败则非零退出、不写库、保留原文不动。
3. **Given** 原文为空、过短或非 UTF-8，**When** 执行 import，**Then** 明确拒绝并指出原因，不产生空树。

---

### User Story 2 - 系统自查保证抽取可靠 (Priority: P1)

作为用户，我不希望手工逐节点核对；import 时系统应自动自查抽取结果与原文的一致性，只有自查通过的时间树才可用于推进工作。

**Why this priority**: 时间树是从用户原文抽取的事实索引，source_span 可逐条机器核对，自查比人工核对更客观且不增加用户负担；自查未通过 MUST NOT 驱动任何调研/世界/仿真。

**Independent Test**: 对一篇正常故事 import，检查输出的自查报告逐项通过且状态即为 ready，全程无人工确认步骤；再构造 span 漂移文本，检查自动重试与拒绝行为。

**Acceptance Scenarios**:

1. **Given** 一篇正常纯文本故事，**When** 执行 import，**Then** 系统自动完成契约结构校验、每节点 source_span 逐字回指原文核对、节点顺序与时间锚点一致性检查、重复人物/地点/道具去重检查，全部通过后树状态为 ready 并输出自查报告，无需人工确认。
2. **Given** 自查发现 source_span 不命中或结构校验失败，**When** 执行 import，**Then** 自动重试抽取与自查一次；仍失败则非零退出、不写库，并列出具体失败节点与检查项。
3. **Given** 不存在自查通过的树（或显式指定未就绪树），**When** 尝试驱动调研/世界/仿真，**Then** 命令拒绝执行并说明树未就绪。

---

### User Story 3 - 按树驱动调研与建世界 (Priority: P2)

作为用户，我希望树里出现的空间/人/物自动汇成调研清单、空间节点自动成为世界锚点，避免把整篇故事重新拆成宽泛题材盲调。

**Why this priority**: 这是「按树推进工作」的前半段；复用既有调研漏斗即可实现，不需要新调研算法。

**Independent Test**: 对同一 ready 树，检查调研清单只含树中出现的空间/人/物且已去重，每个空间节点在世界 config 中有对应 location 锚点。

**Acceptance Scenarios**:

1. **Given** ready 树，**When** 执行 `narrative timeline drive T001 --stage research`，**Then** 从树去重出的查询词经 `brief.execute_brief` 四层漏斗执行，返回逐条 ledger；不绕过缓存/复用/合并逻辑。
2. **Given** ready 树，**When** 执行 `narrative timeline drive T001 --stage world --world-id W001`，**Then** 按空间节点创建/更新世界，节点→资产映射写入 world config，资产修订被正常冻结。
3. **Given** 树中某引用解析不到 asset_id，**When** drive，**Then** 明确报出未解析节点与引用并拒绝该阶段，不静默跳过。

---

### User Story 4 - 按树锚定仿真事件并导出 (Priority: P2)

作为视频管线使用者，我希望仿真事件能锚定回故事时间树的节点，使事件流可对照故事时间线回放，而故事本身不被改写。

**Why this priority**: 没有 node_id 锚点，事件流与故事时间线之间无法对账，树就只是一份死文档。

**Independent Test**: 对锚定后的树跑一次仿真，检查每个事件带合法 node_id，导出 JSONL 按 node_id → tick → seq 排序，且契约校验通过。

**Acceptance Scenarios**:

1. **Given** ready 且已建世界的树，**When** 执行 `narrative timeline drive T001 --stage run --run-id R001 --ticks N`，**Then** 每个时间节点映射到一段 tick 区间，事件带 node_id 且引用真实资产 ID，event 契约校验通过。
2. **Given** run R001 已有事件，**When** 执行 `narrative export R001 --out ...`，**Then** 导出按 node_id → tick → seq 排序，事件只引用 asset_id，不内联外貌文本。
3. **Given** 故事已写死的关键事件，**When** 仿真填充细节，**Then** 节点事实（时间顺序、地点、出场人物、事件类型）不变，不生成与原文冲突的新情节。

---

### Edge Cases

- 原文为空、小于约定最小长度或非 UTF-8 编码：拒绝并说明原因，不写库。
- 文本没有显式时间词，只有叙述顺序：以顺序序号为时间锚点，文本时间可为空，不得编造时间。
- 同一人物/地点/道具多次出现：抽取结果去重，映射到同一 asset_id；不可为每次出场新建资产。
- 新旧文本重复导入同一 tree_id：默认拒绝，需显式 `--overwrite` 才替换，避免覆盖已自查通过的结果。
- source_span 在原文中定位不到（字符偏移漂移）：自查失败并自动重试；仍失败则整体拒绝写库，指出失败节点与检查项。
- 树中引用在库内无对应资产：自查通过并入库（此阶段尚无资产），但 drive 到对应阶段时拒绝执行并说明未解析引用。
- 故事含中文、空格或长路径文件名：import/export 正常处理路径。
- LLM 输出类别漂移、字段缺失：重试一次；仍失败则非零退出，不写半棵树。
- 超长文本：v1 设可配置长度上限，超限明确拒绝并提示拆分，不静默截断。
- 未就绪（自查未通过）的树被 drive：直接拒绝，不产生任何调研/世界/仿真副作用。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 结构变更 MUST 先修订 `schemas/story_tree.schema.json` 并提升版本，再改代码；`event.schema.json` MUST 增加 `node_id` 字段并纳入校验（宪章 I）。
- **FR-002**: 输入 MUST 为 UTF-8 纯文本故事文件；v1 默认长度上限 20000 字（可用环境变量 `STORY_TREE_MAX_CHARS` 覆盖），超限明确拒绝而非截断；v1 MUST NOT 假设分场/剧本格式，不做分场切分，按叙述顺序抽取（见 Assumptions）。
- **FR-003**: 抽取 MUST 经统一 LLM 通道（DeepSeek Flash）做结构化整理，并经 jsonschema 校验；节点 MUST 含文本时间、顺序、空间/人/事/物、source_span 与父子关系。
- **FR-004**: 抽取失败 MUST 重试一次；仍失败 MUST 非零退出且不写库。
- **FR-005**: 树 MUST 存入项目库的 `story_trees` / `story_nodes` 表，且 MUST 只经 `orchestrator/store.py` 的单一入口读写（宪章 III）。
- **FR-006**: import MUST 在写库前自动自查并输出自查报告（逐项结果与失败项）；自查通过 MUST 将树置为 ready 并记录自查时间；MUST NOT 自动触发任何调研/世界/仿真。系统 MUST 提供树 JSON 导出，便于存档和排查。
- **FR-007**: 自查 MUST 至少包含四项：契约结构校验、每节点 source_span 逐字回指原文核对、节点顺序与时间锚点一致性、重复人物/地点/道具去重检查；任一必检项失败即视为自查失败。
- **FR-008**: 自查失败 MUST 自动重试抽取与自查一次；仍失败 MUST 非零退出、不写库，并列出失败节点与检查项；show MUST 输出树内容与最近一次自查报告。
- **FR-009**: drive MUST 先检查树为 ready，否则拒绝执行且不产生副作用。
- **FR-010**: research 阶段 MUST 从树去重出查询词并复用 `brief.execute_brief` 四层漏斗（缓存/清单合并/库内复用/中阈值 attach），MUST NOT 绕过或直接写库。
- **FR-011**: world 阶段 MUST 按空间节点建立/更新世界，并把节点→资产映射写入 world config；资产修订冻结规则保持不变。
- **FR-012**: run 阶段 MUST 将每个时间节点映射为一段 tick 区间；树驱动 run 产出的事件 MUST 带合法 `node_id` 且通过 event 契约校验，非树驱动 run 行为不变。
- **FR-013**: export MUST 按 node_id → tick → seq 排序；事件 MUST 只引用 asset_id，不内联外貌文本。node_id 按节点顺序生成，与 tick 单调一致；无 node_id 的既有事件排序等价于原 tick → seq，不改变既有视频管线消费顺序。
- **FR-014**: CLI 与 MCP MUST 只调用 `orchestrator/workflows.py` 中的编排函数；MCP 工具 MUST 为薄封装，MUST NOT 承载业务逻辑（宪章 II）。
- **FR-015**: 树内容 MUST 只整理故事已有事实，MUST NOT 生成新对白或新情节；细节填充仍由仿真在节点之间完成。
- **FR-016**: `scripts/run_minimal_chain.py`（M1）MUST 保持离线确定性与通过；现有契约、集成与 MCP 测试 MUST 不回归。
- **FR-017**: README、开发手册与 `skills/narrative-sim/SKILL.md` MUST 补充时间树命令、自查门槛与三库边界说明。
- **FR-018**: 时间树是用户已提供原文的机械抽取索引，不是「生成内容」，也不进入正式产出，因此宪章「生成内容人工复核」条款不针对它；其正确性由 FR-007 的客观自查保证。仿真事件若用于正式产出，人工复核约束保持不变，本特性不豁免、不弱化该约束。

### Key Entities

- **故事时间树**: `tree_id`、原文引用、状态（ready）、创建与自查时间、节点集合。
- **时间节点**: `node_id`、顺序序号、文本时间（可空）、source_span、空间/人/事/物引用、父子关系。
- **source_span**: 原文字符起止偏移与原文片段；用于机器逐字回指核对，定位失败即自查失败。
- **就绪状态**: 自查通过后置 ready；只有 ready 树可被 drive。
- **自查报告**: 四项必检检查的逐项结果、失败节点与检查项、自查时间。
- **节点锚点**: 节点到资产（scene/char/prop）或事件的映射；写入 world config 与事件 `node_id`。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 对给定纯文本故事，import 产出的节点数量、时间顺序与四类要素可逐条回指原文，source_span 命中率 100%。
- **SC-002**: 未就绪（自查未通过）的树执行 drive 时，调研/世界/仿真的副作用次数为 0，且返回明确拒绝信息。
- **SC-003**: 同一人物/地点/道具在树中去重后只有一条引用，无重复资产创建。
- **SC-004**: 锚定后事件的 `node_id` 覆盖率 100%，导出顺序满足 node_id → tick → seq，契约校验通过率 100%。
- **SC-005**: M1 回归、现有离线测试、契约守卫与 MCP 测试全部通过。
- **SC-006**: 正常故事 import 全程人工确认步骤为 0，自查报告逐项通过且状态直接为 ready。

## Assumptions

- 输入为 UTF-8 纯文本故事，无分场标记；解析器按叙述顺序抽取，不做剧本格式切分。
- v1 对文本长度设可配置上限，超限拒绝而非静默截断；分块抽取留出后续特性。
- v1 不提供节点级编辑：自查失败或结果不符时用 `--overwrite` 重新 import；节点级修订属后续特性。
- LLM 沿用项目统一 DeepSeek Flash 通道与 `.env` 密钥，不引入新的模型供应商。
- 时间树是故事的事实索引，不是创作产物；节点事实不可由仿真改写，细节由仿真在节点之间填充。
- 本树是用户原文经结构化抽取得到的事实索引，既非「生成内容」也不进入正式产出，故宪章「生成内容人工复核」条款的适用对象不包含它（范围界定，非豁免）；仿真事件若用于正式产出，人工复核约束保持不变（FR-018）。
- 自查以客观可机器核对的证据为准（原文逐字回指、schema 结构、顺序一致性、去重），不依赖主观判断。
- 调研复用既有 `research_brief` / `brief.execute_brief` 漏斗与三库边界，不新增调研数据库或存储路径。
- 特性在分支 `023-story-tree` 上完成，遵循 spec → plan → tasks → implement 全链条。
