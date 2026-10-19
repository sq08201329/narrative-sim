# Feature Specification: TinyTroupe 真后端接入（M2）

**Feature Branch**: `002-tinytroupe-backend`

**Created**: 2026-10-19

**Status**: Draft

**Input**: User description: "M2：实现 orchestrator/persona_tinytroupe.py，实现 PersonaBackend Protocol，TinyPerson 实例按 asset_id 缓存复用、跨回合保持记忆连续性，新增 scripts/run_real_chain.py 仅替换 backend 参数；验收为真后端跑 4 回合产出 ≥5 条事件、契约校验通过、M1 不回归（参考 mydocs 手册 M2）。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 真实角色心智驱动仿真 (Priority: P1)

开发者配好密钥后，运行真后端链路脚本，由真实 LLM 驱动的角色心智（而非 Mock 剧本）
产出 4 回合、不少于 5 条、全部通过事件契约的剧情事件流，并导出 JSONL。

**Why this priority**: 这是项目的核心价值 —— M1 的 Mock 只是脚手架，只有真实角色心智
驱动的仿真才产出有叙事价值的事件流。同时它验证宪章原则 IV 的适配器隔离在真实
第三方库下成立。

**Independent Test**: 配置 `.env` 后运行真后端链路脚本，退出码 0、输出验收信息、
导出文件逐条过契约校验，即独立交付价值。

**Acceptance Scenarios**:

1. **Given** `.env` 已配置有效密钥，**When** 运行真后端链路脚本（4 回合、1 名角色），
   **Then** 产出 ≥5 条事件、逐条通过事件契约校验、导出 JSONL
2. **Given** 同一名角色连续 4 回合仿真，**When** 查看第 2 回合及之后的事件，
   **Then** 角色行为/台词可见地承接了此前回合发生的内容（记忆连续性）
3. **Given** 真后端链路跑过，**When** 运行 M1 最小链路与全量测试，
   **Then** M1 不回归（全部通过）

---

### User Story 2 - 后端一键切换 (Priority: P2)

开发者可以在 Mock 后端与真后端之间切换同一条链路：除注入的后端参数外，
链路代码零改动。

**Why this priority**: 宪章原则 IV 要求后端可互换；这也是离线回归（Mock）与
在线验收（真后端）并存的前提。

**Independent Test**: 对比最小链路脚本与真后端链路脚本，差异仅在后端注入；
分别运行各自通过验收。

**Acceptance Scenarios**:

1. **Given** 已实现的后端切换机制，**When** 对比两条链路脚本，
   **Then** 差异仅体现在后端注入参数上
2. **Given** 无密钥环境，**When** 运行 Mock 链路，**Then** 照常验收通过，
   不触发任何真实 LLM 调用

---

### User Story 3 - 成本可审计 (Priority: P3)

每次真后端仿真运行的 token 用量按运行标识聚合落库，事后可按运行查询成本。

**Why this priority**: 多角色仿真 token 消耗大（手册已知坑 3，宪章原则 VI）。
M2 是首次真实消耗，记账机制必须同步落地，否则成本不可追溯。

**Independent Test**: 跑一次真后端仿真后查询该运行的成本记录，值大于 0 且
与后端统计一致。

**Acceptance Scenarios**:

1. **Given** 一次完成的真后端仿真，**When** 查询该运行的成本记录，
   **Then** 存在非零的聚合数值
2. **Given** Mock 链路运行，**When** 查询其成本记录，**Then** 数值为 0 或无记录，
   不产生虚假记账

---

### Edge Cases

- LLM 超时或返回格式漂移：后端重试与质量校验双保险生效，最终失败时给出明确错误，
  非法事件不得入库
- 角色人格设定缺失关键字段：构建角色心智前经资产契约校验拦截
- `.env` 缺失或密钥无效：明确报错指明缺失/无效的环境变量，不产生隐晦异常
- 真后端运行中断（网络断开）：已入库事件保持完整，不残留半条事件

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 提供真后端实现，满足既有 `PersonaBackend` 接口
  （`act(persona_spec, visible_state)` 返回 `{"kind", "content", "emotion"}`），
  业务代码 MUST NOT 直接依赖 TinyTroupe API（宪章原则 II/IV）
- **FR-002**: 角色心智实例 MUST 按 `asset_id` 缓存复用，跨回合保持记忆连续性，
  MUST NOT 每回合重建实例
- **FR-003**: TinyTroupe 依赖 MUST 以带具体 commit 的 git URL 声明于
  `pyproject.toml` 并锁入 `uv.lock`；MUST NOT 使用 PyPI 占位包（宪章原则 IV/V）
- **FR-004**: TinyTroupe 配置文件 MUST 位于项目根目录；真后端脚本的运行前提是
  工作目录为项目根目录，否则 MUST 明确报错
- **FR-005**: 真后端链路脚本 MUST 与最小链路脚本同构，差异仅在后端注入
- **FR-006**: 动作解析 MUST 具备重试机制与质量校验；最终不合格的动作 MUST NOT
  写入事件库
- **FR-007**: 系统 MUST 按运行标识聚合 token 用量并写入运行记录（宪章原则 VI）
- **FR-008**: 真后端验收 MUST 同时满足：4 回合产出 ≥5 条事件、逐条契约校验通过、
  M1 全量测试不回归
- **FR-009**: 缺少或无效的密钥/服务地址 MUST 触发指明具体环境变量的明确错误
- **FR-010**: 真后端产出的事件 MUST 与 Mock 产出共用同一事件契约与导出格式；
  事件 MUST 只引用资产 ID

### Key Entities *(include if feature involves data)*

- **角色心智实例缓存**：`asset_id` → 角色心智实例的映射，生命周期为一次仿真运行，
  是记忆连续性的载体（进程内结构，不入库）
- **运行成本记录**：Run 实体的既有字段（`token_cost`），本特性首次写入真实数值

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 配置密钥后，一次 4 回合单角色真后端仿真在 10 分钟内完成，
  产出 ≥5 条事件且 100% 通过契约校验
- **SC-002**: 真后端产出的事件在语义上承接前序回合（抽查可见承接关系），
  而非每回合相互独立的模板化输出
- **SC-003**: M1 回归基线 100% 通过（全量测试 + 最小链路脚本）
- **SC-004**: 每次真后端运行的成本记录可查询且数值大于 0；Mock 运行不产生
  虚假成本记录

## Assumptions

- 开发者持有有效 DeepSeek 密钥并已填入 `.env`（本特性不含密钥分发）
- TinyTroupe API 仍在快速迭代：接入点以具体 commit 为准，升级属于独立决策
- M2 验收口径与 M1 对齐：单角色、4 回合、≥5 事件；多角色交错对话的
  深度信息流（角色互相可见性规则）属 M4 世界引擎范畴
- 本特性不做调研管线（M3）、不接 WorldSeed（M4）、不做 MCP Server（M5）
- 运行环境为本地 Windows 开发机；LLM 调用需可访问 DeepSeek 服务
- 本地开源项目副本（见 `mydocs/opensource_repos_dir.md`）可供实现阶段参考
  TinyTroupe 相关用法
