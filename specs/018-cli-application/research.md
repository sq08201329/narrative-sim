# Phase 0 Research: 统一 CLI 应用

## CLI 解析与入口

- **Decision**: 使用标准库 `argparse`，在 `pyproject.toml` 注册 `narrative = "orchestrator.cli:main"`。
- **Rationale**: 现有脚本已经使用 argparse；无需引入 Typer/Click，且同一 `main()` 可供后续 PyInstaller 使用。
- **Alternatives considered**: 继续多个脚本（不满足统一入口）；Typer（增加非必要依赖）。

## 输出与错误语义

- **Decision**: 除 MCP 外，成功业务结果以单个 JSON 对象写 stdout；帮助由 argparse 输出，诊断写 stderr。成功为 0，运行失败为 1，参数错误沿用 argparse 的 2。
- **Rationale**: 同时便于人工查看和自动化解析；MCP 的 stdout 必须保留给协议。
- **Alternatives considered**: 人读文本加 `--json` 双格式（首版非必要）；所有信息混写 stdout（不利于脚本与 MCP）。

## 配置与数据路径

- **Decision**: `NARRATIVE_HOME` 默认项目根目录；数据库默认 `<home>/data/projects/linan.db`，日志为 `<home>/logs`，服务状态为 `<home>/run`。全局 `--home`、`--db` 优先于同名环境配置。
- **Rationale**: 保留当前数据和目录布局，不迁移真实库；统一 CLI 启动的 MCP 与直接业务命令的数据集。
- **Alternatives considered**: 立即迁移到 `%LOCALAPPDATA%`（属于后续安装包特性，会改变现有数据位置）；继续使用各脚本默认库（会写错数据集）。

## 进程所有权与生命周期

- **Decision**: 使用 psutil 核验 PID、进程创建时间和命令行；`services.py` 原子写入受管服务状态。启动顺序为 embedding → gptr-mcp → narrative MCP，停止反向执行。
- **Rationale**: 仅检查 PID 或端口存在误停风险；psutil 已在锁定依赖树中且支持 Windows，提升为直接依赖即可获得明确的所有权判断。
- **Alternatives considered**: tasklist/PowerShell CIM（命令行核验脆弱且发行版依赖 PowerShell）；只匹配端口（违反外部进程保护要求）。

## 外部服务与兼容

- **Decision**: 保留 `scripts/start_stack.ps1`；Python 服务管理复用其环境口径，`GPTR_ROOT`、`EMBEDDING_ROOT`、`LITERT_LM` 可配置，当前本机路径仅作为兼容默认值。
- **Rationale**: 本特性不改变外部项目布局，也能在当前机器运行；后续 workspace/打包特性再移除本机路径默认值。
- **Alternatives considered**: 本特性搬迁全部外部项目（超出范围）；从 CLI 调 PowerShell（不满足独立入口方向）。

## 业务复用与验收

- **Decision**: 将 MCP 工具中已有的世界创建、运行和导出编排提取为 Orchestrator 内部可复用函数，CLI 与 MCP 共同调用；调研直接复用 `research_asset`。
- **Rationale**: 防止 CLI 与 MCP 逐渐形成不同行为，同时保持工具语义不变。
- **Alternatives considered**: CLI 调 MCP 客户端执行本地业务（要求所有命令都先启动服务）；复制 MCP 工具体（产生第二套业务实现）。

所有 Technical Context 未知项均已解决，无 NEEDS CLARIFICATION。
