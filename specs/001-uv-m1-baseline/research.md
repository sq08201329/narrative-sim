# Phase 0 Research: uv 项目脚手架与最小仿真链路（M1）基线

技术上下文中无 NEEDS CLARIFICATION 项（语言、依赖、存储、测试框架均由宪章与手册锁定）。
以下为本次规划做出的设计决策与依据。

## D1: 项目形态 —— application 布局，不打包发布

- **Decision**: `uv init` 采用 application 形态；`orchestrator/` 作为顶层包被
  `scripts/` 直接 import，不做 src-layout、不配置打包发布。
- **Rationale**: M1 的价值是"一条可运行的链路"，不是可分发的库；application 布局
  与手册目标目录结构（第 7 节）一致，减少与后续里程碑的迁移成本。
- **Alternatives considered**: src-layout + 可安装包 —— 对内部工具属过度设计，
  且会让 `uv run python scripts/run_minimal_chain.py` 的验收路径变复杂，拒绝。

## D2: 测试框架 —— pytest（dev 依赖）

- **Decision**: `uv add --dev pytest`；契约守卫用例放 `tests/contract/`，
  全链路用例放 `tests/integration/`。
- **Rationale**: spec 的 FR-006（非法数据被拒）与 FR-008（全链路验收）需要
  可重复执行的自动化检验，不能只靠人肉跑脚本；pytest 是 Python 事实标准。
- **Alternatives considered**: 只写脚本断言、不引入测试框架 —— 无法满足
  spec SC-002/SC-003 的"100% 确定性 / 100% 拒绝"的持续验证要求，拒绝。

## D3: llm.py 在 M1 的去留 —— 保留为"接缝模块"

- **Decision**: 保留 `orchestrator/llm.py`，但 M1 链路不调用它。模块可 import
  （不读密钥）；首次调用时若无密钥则抛出指明缺失环境变量的明确错误。
- **Rationale**: 宪章原则 VI 要求 LLM 只经统一接缝接入；接缝随基线一起落地，
  M2 只需换后端调用而不新增结构。懒加载密钥保证 FR-010（离线无密钥可运行）成立。
- **Alternatives considered**: 整个模块推迟到 M2 —— 会导致 M1 代码里没有任何
  LLM 边界，后续容易在别处直接 new client，违反原则 VI，拒绝。

## D4: 两张契约 JSON Schema —— 按手册字段口径重新编写

- **Decision**: `asset.schema.json` / `event.schema.json` 依据手册 3.1 / 3.2 的
  字段表、ID pattern、必填规则重新编写完整 JSON Schema（手册未附 JSON 全文）。
- **Rationale**: 用户明确手册仅作参考、代码不照搬；Schema 本就是接口定义，
  按字段口径重写等价于"按文档实现接口"。
- **Alternatives considered**: 留 TODO 等后续补 —— 契约先行是原则 I 的硬门槛，
  无 Schema 则 store 无从校验，拒绝。

## D5: 重复 run_id 的行为 —— 拒绝并报错

- **Decision**: `create_run` 对已存在的 run_id 抛出明确错误；不重跑覆盖。
- **Rationale**: 事件按 `run_id + tick + seq` 排序，静默重跑会造成同键事件混杂、
  因果引用错乱；显式失败符合"契约守卫"精神（spec Edge Cases）。
- **Alternatives considered**: 允许覆盖（先删后写）—— 破坏审计性，拒绝。

## D6: 校验错误的可读性 —— 指明字段路径

- **Decision**: 契约校验失败时，错误信息包含 JSON 路径与不合规原因
  （如 `$.appearance: 'visual_prompt' is a required property`）。
- **Rationale**: spec US2 要求"指出不合规之处"；jsonschema 的 ValidationError
  天然携带路径，包装一层即可。
- **Alternatives considered**: 直接抛原始异常 —— 顶层信息含内部细节且对
  中文开发者不友好，拒绝。

## D7: 本特性不做什么（范围护栏）

- 不接 TinyTroupe / 真实 LLM（M2）；不写调研管线（M3）；不接 WorldSeed（M4）；
  不做 MCP Server（M5）；不做导出 expand 模式（M6）。
- 不使用本地开源项目副本（`my_mas` / `my-gpt-research`），M1 为 Mock 后端，
  无需参考其实现。
- `config.ini`（TinyTroupe 配置）本特性不创建 —— 它只服务于 M2 的真后端，
  M1 引入它会造成"有配置无代码"的悬空状态。
