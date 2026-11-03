# Implementation Plan: Windows 独立应用

**Branch**: `020-standalone-app` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/020-standalone-app/spec.md`

## Summary

以 PyInstaller onedir 构建 `NarrativeSim.exe`，通过同一 EXE 的内部子命令运行调研 MCP，叙事 MCP 沿用现有命令。增加冻结资源根与用户数据目录适配，收集动态导入和组件资源，并由统一构建脚本生成目录及 ZIP。开发模式路径和现有业务契约保持不变。

## Technical Context

**Language/Version**: Python 3.12，uv workspace

**Primary Dependencies**: PyInstaller（开发依赖）、现有 CLI/FastMCP/WorldSeed/GPT-Researcher/TinyTroupe、psutil

**Storage**: 现有 SQLite；冻结默认数据根为 `%LOCALAPPDATA%/NarrativeSim`，开发默认仍为仓库根

**Testing**: pytest 路径/子进程契约；真实冻结 EXE 的 CLI、Mock、stdio MCP 与服务生命周期验收

**Target Platform**: Windows 10/11 x64，onedir 免安装 ZIP

**Project Type**: 独立本地 CLI 与多进程 MCP 应用

**Performance Goals**: 避免 onefile 重复解压；构建只复制必要运行资源，不包含真实用户数据

**Constraints**: 无 GUI/安装器/下载器；不调用系统 Python/uv；不在包内写配置或数据库；stdio  stdout 专用于协议

**Scale/Scope**: 1 个公开 EXE、1 个内部调研子命令、3 个服务、3 类数据库

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I 契约先行**：Schema 原样作为资源打包，入库/导出仍走既有校验。通过。
- **II 单一胶水层**：冻结适配只改 Orchestrator 与构建文件，第三方业务逻辑不新增跨库调用。通过。
- **III 存储单一入口**：数据库路径改变但读写仍经 Store/db.corpus；服务状态仍由 services.py 管理。通过。
- **IV Mock 基线**：开发 M1 不变，冻结 Mock 独立验收；TinyTroupe commit 不变。通过。
- **V UV 依赖**：PyInstaller 经 `uv add --dev` 并由锁文件固定。通过。
- **VI 密钥与成本**：构建排除 `.env`；冻结配置只从用户目录/环境读取，成本记录不变。通过。
- **质量门禁**：独立分支，最终跑现有离线套件、M1、构建及冻结验收。通过。

## Project Structure

### Documentation (this feature)

```text
specs/020-standalone-app/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── distribution.md
└── tasks.md
```

### Source Code (repository root)

```text
packaging/
└── narrative.spec         # onedir、动态导入、资源与许可证收集

scripts/
└── build_standalone.py    # 构建、清理安全边界、ZIP 与构建信息

orchestrator/
├── cli.py                 # 冻结 HOME、配置、内部 gptr 子命令
├── services.py            # 冻结子进程回调 sys.executable
├── store.py               # 冻结 Schema 资源根
└── persona_tinytroupe.py  # 日志写用户目录

tests/
├── contract/test_standalone.py
└── integration/test_standalone.py

dist/NarrativeSim/         # 忽略的运行产物
dist/NarrativeSim-windows-x64.zip
```

**Structure Decision**: 保留单仓库与统一 CLI，只增加冻结边界和构建文件，不引入第二应用或 GUI 框架。
