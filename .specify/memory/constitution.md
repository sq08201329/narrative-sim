<!--
Sync Impact Report
==================
版本变更: 模板占位 (0.0.0) → 1.0.0
变更类型: 初始批准。模板占位章节全部替换为项目实义条款，故按 MAJOR 计。
修改的原则:
  - [PRINCIPLE_1_NAME] → I. 契约先行（Contract First）
  - [PRINCIPLE_2_NAME] → II. 单一胶水层（Orchestrator as Sole Glue）
  - [PRINCIPLE_3_NAME] → III. 存储单一入口（Single Writer to Storage）
  - [PRINCIPLE_4_NAME] → IV. 适配器隔离与 Mock 基线（Adapter Isolation）
  - [PRINCIPLE_5_NAME] → V. UV 统一依赖管理（UV-Only Dependencies）
新增原则: VI. 密钥与成本边界（Secrets & Cost Boundary）
新增章节: 技术栈与运行环境约束；开发工作流与质量门禁
移除章节: 无
待办:
  - TODO(GIT_REPO): 当前目录尚未初始化 git 仓库，"一个特性一个分支"无法执行；
    需先建立仓库与 main 基线，再开始第一个特性。
  - 参考文档 mydocs/叙事仿真系统开发手册.md 的 4.1 / 4.2 节仍写 pip install，
    与本宪章原则 V 冲突，以本宪章为准；手册下次修订时同步。
-->

# 叙事仿真系统（narrative-sim）Constitution

## Core Principles

### I. 契约先行（Contract First，不可妥协）

`schemas/asset.schema.json` 与 `schemas/event.schema.json` 是所有模块之间唯一的接缝。

- 结构变更 MUST 先修订 Schema 并提升其版本，再改代码；MUST NOT 先改代码再补 Schema。
- 资产入库与事件导出 MUST 经 `jsonschema` 校验；校验失败 MUST 直接拒绝，MUST NOT 降级放行。
- 事件流中 MUST 只出现 `asset_id` 引用，MUST NOT 内联外貌文本。
- Schema 变更 MUST 附带迁移方案，并保证 M1 回归基线通过。

理由：视频管线要在零依赖前提下直接消费 JSONL，契约一旦漂移，跨镜头一致性即断裂。

### II. 单一胶水层（Orchestrator Is the Only Glue）

- 外部开源项目（SearXNG / Crawl4AI / GPT-Researcher / TinyTroupe / WorldSeed）之间
  MUST NOT 直接 import；所有跨库信息 MUST 经 Orchestrator 转手。
- 每个外部库 MUST 封装在 Orchestrator 内的适配器之后（如 `PersonaBackend` Protocol）；
  业务代码 MUST NOT 直接依赖第三方 API。
- MCP Server MUST 是 Orchestrator 方法的薄封装，MUST NOT 承载业务逻辑。
- 新增跨库数据流 MUST 落在 `orchestrator/`，MUST NOT 写进第三方包或 `scripts/`。

理由：接缝只有一处，替换任一开源组件时才不需要改动其他三层。

### III. 存储单一入口（Single Writer to Storage）

- 只有 `orchestrator/store.py` MAY 读写 SQLite；其他模块 MUST 通过 Store 接口访问。
- 数据库 MUST 是各管线之间的共享记忆；MUST NOT 用文件或进程内状态替代持久世界状态。
- 世界状态 MUST 每回合落入 `worlds.state`，以支撑断点续跑。
- DDL 变更 MUST 幂等（`CREATE TABLE IF NOT EXISTS`），MUST NOT 破坏既有数据。

理由：多入口写库会让"断点续跑"与"按 run_id 对账"同时失效。

### IV. 适配器隔离与 Mock 基线（Adapter Isolation & Mock Baseline）

- TinyTroupe 调用 MUST 全部封在适配器内，并在依赖声明中 pin 到具体 commit；
  MUST NOT 依赖 PyPI 上的 `tinytroupe` 占位包。
- `PersonaBackend` MUST 保持 Protocol 形态，Mock 与真后端可互换；切换只允许改注入参数。
- `scripts/run_minimal_chain.py`（M1）MUST 始终可离线、确定性运行，作为回归基线；
  任何改动后 MUST 重跑且不回归。
- 真后端验收 MUST 同时满足：事件数 ≥ 5、契约校验通过、M1 不回归。
- 运行 TinyTroupe 相关脚本时 cwd MUST 为项目根目录（否则读不到 `config.ini`）。

理由：TinyTroupe 官方明示 API 仍在快速迭代，适配器边界是唯一的止漏层。

### V. UV 统一依赖管理（UV-Only Dependencies，不可妥协）

- 依赖 MUST 由 uv 创建与管理：`pyproject.toml` 声明、`uv.lock` 锁定，两者 MUST 入库。
- 增删与升级依赖 MUST 使用 `uv add` / `uv add --dev` / `uv remove` / `uv sync`；
  MUST NOT 使用裸 `pip install`，MUST NOT 手工编辑锁文件。
- 所有脚本与测试 MUST 通过 `uv run` 执行
  （如 `uv run python scripts/run_minimal_chain.py`）。
- Python 版本 MUST 在 `pyproject.toml` 的 `requires-python` 中声明；虚拟环境由 uv 管理，
  MUST NOT 提交 `.venv/`。
- 无法从 PyPI 获取的依赖（如 TinyTroupe）MUST 以带 commit 的 git URL 写入
  `pyproject.toml`，MUST NOT 用 `pip install --no-deps` 临时补包。

理由：手册旧流程的 pip 手工补包不可复现，也无法把 commit pin 落到版本控制。

### VI. 密钥与成本边界（Secrets & Cost Boundary）

- 模型名与 API key MUST 只出现在 `.env` / `config.ini`；MUST NOT 落入代码、测试或文档示例。
- `.env` MUST 在 `.gitignore` 中；仓库只保留 `.env.example`。
- LLM MUST 统一经 DeepSeek Flash（OpenAI 兼容协议）接入，MUST NOT 在代码中硬编码其他模型。
- token 用量 MUST 按 `run_id` 聚合写入 `runs.token_cost`；批量仿真 MUST 支持 fast/smart 分级路由。

理由：成本与凭据是仿真批量运行的致命变量，必须可审计、可重定向。

## 技术栈与运行环境约束

- 运行时 MUST 为 uv 管理的 Python 3.12；存储 MUST 为 SQLite（Python 内置）；
  MUST NOT 引入 Docker 或外部数据库服务。
- 结构化输出 MUST 双重校验：TinyTroupe `ActionGenerator` 质量校验保持开启，
  且 Orchestrator 再做一次 Schema 校验。
- 外部服务地址（SearXNG / DeepSeek）MUST 从环境变量读取，MUST NOT 硬编码。
- 生成内容 MUST 经人工复核后方可用于正式产出（TinyTroupe 仅限研究与仿真用途）。

## 开发工作流与质量门禁

- 一个特性 MUST 对应一个分支：分支从 `main` 切出，合并后删除；
  MUST NOT 在 `main` 上直接开发。
- 分支名 MUST 携带特性序号与短名（如 `003-research-pipeline`），
  并与 `specs/` 下的特性目录保持一致。
- 每个特性 MUST 走完整链条：`specify → plan → tasks → implement`，
  MUST NOT 跳过 spec 直接写代码。
- 提交 MUST 单一意图、可回滚；合并前 MUST 通过 `uv run` 下的检查
  （M1 回归 + 契约校验）。
- `mydocs/叙事仿真系统开发手册.md` 是实现参考；与宪章冲突时 MUST 以宪章为准，
  并回写手册以消除分歧。

## Governance

- 本宪章 supersedes 其他实践约定；与 `mydocs/` 手册冲突时以宪章为准。
- 修订 MUST 走 PR：说明动机、影响范围与迁移方案，合并即生效。
- 版本 MUST 遵循语义化：MAJOR 为原则删除/重定义或向后不兼容；MINOR 为新增原则、
  新增章节或实质性扩展；PATCH 为措辞澄清。
- 每份 spec / plan MUST 声明对本宪章的符合性；违反 MUST 在 plan 中给出理由，
  否则阻塞合并。
- 合规审查 MUST 在 `/skill:speckit-analyze` 与代码评审两个环节执行。
- 运行时开发指引见 `mydocs/叙事仿真系统开发手册.md`（实现细节）与本文件（治理约束）。

**Version**: 1.0.0 | **Ratified**: 2026-10-19 | **Last Amended**: 2026-10-19
