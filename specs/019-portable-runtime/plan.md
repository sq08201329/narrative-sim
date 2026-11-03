# Implementation Plan: 可迁移运行时

**Branch**: `019-portable-runtime` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/019-portable-runtime/spec.md`

## Summary

将 WorldSeed 与 gptr-mcp 收拢为 uv workspace 成员，根项目一次 `uv sync` 安装全部 Python 运行依赖。服务管理改为仓库相对路径，模型通过显式文件配置；三类数据库均由 `NARRATIVE_HOME` 派生且保留独立覆盖。保留上游版本、MIT 许可证和 WorldSeed 中文补丁，不改变业务 Schema、CLI 命令或 MCP 工具语义。

## Technical Context

**Language/Version**: Python 3.12，uv workspace

**Primary Dependencies**: 现有 FastMCP Slim、TinyTroupe、GPT-Researcher、WorldSeed；psutil；标准库 pathlib/subprocess

**Storage**: 现有 SQLite 三库；JSON 服务状态仍由 `orchestrator/services.py` 独占

**Testing**: pytest 契约/集成测试；路径守卫；隔离副本安装与离线 CLI 链路

**Target Platform**: Windows 10/11 x64，中文/空格/跨磁盘路径

**Project Type**: 多包本地 CLI 与 MCP 服务仓库

**Performance Goals**: 不增加业务运行路径；服务状态避免不必要的全系统进程扫描

**Constraints**: 无 Docker；不提交模型/数据库/密钥；不自动迁移数据；不使用第二套虚拟环境；上游组件边界不变

**Scale/Scope**: 2 个收拢组件、1 个现有插件、3 类数据库、3 个本地服务

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I 契约先行**：不修改资产/事件 Schema，既有校验不变。通过。
- **II 单一胶水层**：组件代码物理收拢但仅由现有 Orchestrator 适配器调用，跨库数据流不进入第三方包。通过。
- **III 存储单一入口**：戏库/文库入口不变；仅统一路径解析，无新存储域。通过。
- **IV 适配器与 Mock**：TinyTroupe 仍固定 commit；离线 Mock 不依赖模型和调研服务。通过。
- **V UV 统一依赖**：内部组件使用 workspace 相对来源，锁文件由 uv 生成，不手工编辑。通过。
- **VI 密钥与成本**：凭据仍只经 `.env`/环境，模型名与成本口径不变。通过。
- **质量门禁**：独立分支，最终执行干净副本安装、全部离线测试、M1 和 MCP 回归。通过。

## Project Structure

### Documentation (this feature)

```text
specs/019-portable-runtime/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── paths.md
└── tasks.md
```

### Source Code (repository root)

```text
packages/
├── worldseed/             # 上游 4ffeabf + 已留档 UTF-8 补丁
│   ├── src/worldseed/
│   ├── shared/languages.json
│   ├── configs/
│   ├── pyproject.toml
│   └── LICENSE
├── gptr-mcp/              # 上游 6388477
│   ├── server.py
│   ├── utils.py
│   ├── pyproject.toml
│   └── LICENSE
└── gpt-researcher/        # 镜像 27c0f42，含现有调研链路修复
    ├── gpt_researcher/
    ├── pyproject.toml
    └── LICENSE

plugins/gptr-deepseek-retriever/
orchestrator/
├── cli.py                 # 统一剧目库路径并传给子进程
├── corpus.py              # CORPUS_DB 由 NARRATIVE_HOME 派生
└── services.py            # 内部 gptr 路径 + 显式模型文件

scripts/start_stack.ps1    # 保留参数，转为统一 CLI 薄入口
pyproject.toml             # workspace 成员与相对 sources
uv.lock
.env.example
```

**Structure Decision**: 使用 uv workspace 多包仓库；收拢运行必需源码与资源，不复制外部项目的虚拟环境、日志、前端、AOCI 或无关工作文件。
