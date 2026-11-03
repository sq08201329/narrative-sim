# Implementation Plan: 统一 CLI 应用

**Branch**: `018-cli-application` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-cli-application/spec.md`

## Summary

提供 `narrative` 单一命令入口，以 `argparse` 封装现有调研、世界、仿真、导出和 MCP 能力；以 Python 服务管理替代发行路径对 PowerShell 的依赖。统一 `NARRATIVE_HOME`、数据库、日志和运行状态解析，业务结果输出 JSON，诊断输出到 stderr。所有业务调用复用 Orchestrator，资产/事件 Schema 与 MCP 工具语义不变。

## Technical Context

**Language/Version**: Python 3.12，由 uv 管理

**Primary Dependencies**: argparse（标准库）、现有 Orchestrator/FastMCP、python-dotenv、psutil（提升为直接依赖）

**Storage**: 现有 SQLite；新增仅由 `orchestrator/services.py` 管理的 JSON 服务运行状态，不改变世界/资产存储契约

**Testing**: pytest 契约与集成测试；CLI 子进程离线验收；真实服务管理以可控测试进程验证

**Target Platform**: Windows 10/11 x64，项目根目录运行；兼容中文和含空格路径

**Project Type**: 本地 CLI 与 MCP 服务

**Performance Goals**: 本地状态查询 2 秒内返回；服务启动沿用现有各项就绪超时，不在未就绪时报告成功

**Constraints**: 无新 GUI/打包范围；无密钥输出；离线 Mock 基线不依赖真实服务；只能终止经 PID、创建时间和命令行核验的受管进程

**Scale/Scope**: 单用户、单技术栈实例；3 个现有服务及 6 类业务命令

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I 契约先行**：不修改资产/事件 Schema；导出仍经现有 Store 复验。通过。
- **II 单一胶水层**：CLI 与服务管理均位于 `orchestrator/`；不跨库直接调用，不在第三方包写业务。通过。
- **III 存储单一入口**：SQLite 仍只经 `orchestrator/store.py` / `db/corpus.py`；服务 PID 元数据仅由 `services.py` 读写，不替代持久世界状态。通过。
- **IV 适配器隔离与 Mock 基线**：CLI 注入现有 Mock/TinyTroupe 后端，M1 保持离线确定性。通过。
- **V UV 统一依赖**：入口在 `pyproject.toml` 注册，psutil 经 `uv add` 声明并更新 `uv.lock`。通过。
- **VI 密钥与成本边界**：从 `.env`/环境读取配置，不回显密钥；真实仿真仍记录 token 成本。通过。
- **工作流与质量门禁**：在 `018-cli-application` 分支执行完整 spec → plan → tasks → implement，合并前跑 M1、契约与 CLI 验收。通过。

## Project Structure

### Documentation (this feature)

```text
specs/018-cli-application/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── cli.md
└── tasks.md             # 由 /skill:speckit-tasks 生成
```

### Source Code (repository root)

```text
orchestrator/
├── cli.py               # argparse 入口、命令分派、JSON 结果与错误码
├── services.py          # 技术栈启停、健康检查、进程归属与运行状态
├── mcp_server.py        # 复用现有业务行为，不新增第二套实现
└── ...

scripts/
├── run_mcp_server.py    # 保留兼容入口
└── start_stack.ps1      # 保留开发环境兼容入口

tests/
├── contract/
│   └── test_cli.py      # 参数、输出、错误码、业务接缝与路径隔离
└── integration/
    └── test_cli.py      # 离线工作流与受管服务生命周期

pyproject.toml           # narrative console script + psutil 直接依赖
uv.lock                  # uv 自动更新
.env.example             # NARRATIVE_HOME 与服务位置配置示例
```

**Structure Decision**: 沿用 application 布局；新增代码只在 Orchestrator 和既有测试层，不引入新应用包或业务存储入口。
