# Feature Specification: 接入 WorldSeed 世界引擎

**Feature Branch**: `006-worldseed-integration`

**Created**: 2026-10-20

**Status**: Draft

**Input**: User description: "M4 接入 WorldSeed：从资产库组装世界配置（角色、场景、
信息不对称规则），仿真循环改由 WorldSeed 引擎驱动；事件翻译逻辑（emit/shot_hint
映射）保留复用；每回合结束把世界状态快照写入 worlds.state（断点续跑基础）；
WorldSeed 是唯一世界状态真相源，角色记忆每回合从它同步；不破坏 M1-M3/005 既有
验收。（mydocs 手册 M4 节仅作参考，引擎形态以本地副本源码调研为准。）"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 资产组装世界并跑通引擎 (Priority: P1)

用资产库里的角色与场景（含 004/005 调研入库的真实资产）组装出一份
WorldSeed 世界配置，引擎驱动仿真跑若干回合，产出的事件流照常通过
事件契约校验、照常入库、照常可导出。

**Why this priority**: 这是本特性的全部价值 —— 目前仿真循环是 001 手写的
最简 tick（角色轮流说话），WorldSeed 提供规则、私密信息、行动与后果的
完整世界模型，叙事质量与可控性都依赖它。

**Independent Test**: 以资产库现存资产组装世界，引擎驱动跑 ≥4 回合，
验证事件数、契约校验与导出均与既有链路一致。

**Acceptance Scenarios**:

1. **Given** 资产库中有 ≥1 角色与 ≥1 场景资产，**When** 组装世界配置并
   启动仿真，**Then** 引擎按配置驱动回合推进，产出事件全部通过事件契约
   校验并入库
2. **Given** 世界配置包含信息不对称规则（不同角色掌握不同私密信息），
   **When** 引擎运行，**Then** 各角色可见状态按规则区分（可经角色输入
   或引擎状态核验），不存在全员上帝视角

---

### User Story 2 - 状态快照与断点续跑 (Priority: P2)

每回合结束把世界状态快照持久化；仿真中断后能从最近快照继续跑，
不必从零重演，且续跑产出的事件编号与此前连续。

**Why this priority**: 长仿真（几十上百回合）必然会被中断（成本、故障、
人工暂停）；没有快照续跑，长仿真就只是演示品。worlds.state 字段
从 001 起就为此预留。

**Independent Test**: 跑 3 回合中断，从快照续跑 2 回合，验证总事件流
与一口气跑 5 回合的形态一致（编号连续、契约通过、无重复无遗漏）。

**Acceptance Scenarios**:

1. **Given** 仿真已运行若干回合，**When** 查看持久层，**Then** 每回合均有
   世界状态快照可查，且快照足以重建引擎状态
2. **Given** 仿真在第 N 回合后中断，**When** 从快照续跑，**Then** 引擎从
   第 N+1 回合继续，事件编号连续、世界观状态无回退

---

### User Story 3 - 事件翻译复用与旧链路基线 (Priority: P3)

引擎到事件流的翻译沿用 001/002 的事件形态与 shot_hint 映射口径；
WorldSeed 的全部接触面集中在适配器内；M1 最小链路与 M2 TinyTroupe
真后端作为基线保留可运行（或被明确替代的口径需文档化）。

**Why this priority**: 事件契约是下游（导出、视频管线）的稳定承诺，
引擎更换不能涟漪出去；旧链路是回归基准与排障对照。

**Independent Test**: M1/M2 离线测试全绿；真后端链路（或其后继形态）
验收通过；grep 验证 WorldSeed 接触面只在适配器模块。

**Acceptance Scenarios**:

1. **Given** WorldSeed 链路已实现，**When** 运行 M1/M2 离线测试套件，
   **Then** 100% 通过（契约与基线行为不回归）
2. **Given** 引擎事件到契约事件的翻译，**When** 映射角色行动/环境变化，
   **Then** 事件 kind 与 shot_hint 口径与 001 既定映射一致

---

### Edge Cases

- 资产库为空或缺角色：组装阶段明确失败并指出缺什么，不启动引擎
- 引擎回合产出无法映射为契约事件的内容：翻译层拦截并明确记录，
  不产生残缺事件入库
- 快照损坏或版本不兼容：续跑明确报错，不静默以损坏状态继续
- 同一 world_id 重复启动：按口径拒绝或显式重置（与 002 真链路同口径）

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 能从资产库组装世界配置（角色、场景、信息不对称
  规则），配置缺失必要资产时 MUST 明确失败并指出缺口
- **FR-002**: 仿真回合 MUST 由 WorldSeed 引擎驱动推进；引擎产出的内容
  MUST 经翻译层映射为契约事件后入库（FR 翻译口径同 001）
- **FR-003**: WorldSeed MUST 是世界状态的唯一真相源；角色可见状态与记忆
  同步 MUST 每回合从引擎状态派生，MUST NOT 在适配器内另存平行状态
- **FR-004**: 每回合结束 MUST 持久化世界状态快照（worlds.state），
  快照 MUST 足以支持断点续跑
- **FR-005**: 续跑 MUST 从最近快照恢复引擎状态，事件编号与此前连续，
  MUST NOT 从零重演已有回合
- **FR-006**: WorldSeed 的全部接触面 MUST 集中在适配器模块内
  （宪章原则 II）；离线测试 MUST 有 Mock 基线（宪章原则 IV）
- **FR-007**: 本特性 MUST NOT 改动资产/事件契约；写入 MUST 只经 store.py
  （宪章原则 III）；M1、M2、003、004、005 既有验收 MUST 不回归
- **FR-008**: 引擎/LLM 配置 MUST 走环境变量（宪章原则 VI）；
  引擎若引入新依赖 MUST 经 uv 管理（宪章原则 V）

### Key Entities *(include if feature involves data)*

- **世界配置**：角色列表、场景、信息不对称规则、回合参数 —— 由资产库组装，
  随 worlds 记录持久化
- **世界状态快照**：引擎每回合的完整状态 —— 持久化于 worlds.state，
  断点续跑的恢复点
- **契约事件**：引擎内容经翻译层映射的产物 —— 形态与 001 既定契约一致，
  编号跨续跑连续

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 用资产库真实资产组装世界并引擎驱动跑 ≥4 回合，产出 ≥5 条
  契约校验通过的事件并入库导出（与 002 验收同量级）
- **SC-002**: 信息不对称配置下，至少两名角色的可见状态存在可核验的差异
- **SC-003**: 3 回合中断 + 续跑 2 回合的事件流与连续跑 5 回合相比：
  编号连续、零重复、契约 100% 通过
- **SC-004**: M1 / M2 / 003 / 004 / 005 离线回归 100% 通过
- **SC-005**: WorldSeed 接触面 100% 位于适配器模块内；无硬编码配置

## Assumptions

- WorldSeed 的具体接入形态（库调用 / 配置格式 / 回合 API / 快照格式）以
  本地副本（`my_mas/WorldSeed`）源码调研为准，plan 阶段确定；本规格不锁定
- 角色智能体在引擎内的承载方式（TinyTroupe 嵌入引擎 vs 引擎原生 Agent）
  是 plan 阶段的核心决策点；手册的"TinyPerson 记忆每回合从引擎同步"为
  参考口径，不作强制
- WorldSeed 为 MIT 许可（本地副本 LICENSE），引入无法律障碍
- 引擎驱动的真机验收仍需 DeepSeek 密钥；LLM 成本与 002 同量级或更高，属预期
- 本特性不做：引擎的 Web 前端（副本含 frontend/）、多世界并行、
  人工介入（intervene）通道、M5 的 MCP 封装
