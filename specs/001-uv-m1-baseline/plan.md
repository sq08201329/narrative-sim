# Implementation Plan: uv 项目脚手架与最小仿真链路（M1）基线

**Branch**: `001-uv-m1-baseline` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-uv-m1-baseline/spec.md`

## Summary

建立 uv 管理的 Python 项目骨架，并落地项目核心链路的最小可运行形态：
两张数据契约（资产 / 事件）+ SQLite 四类存储 + 唯一存储接口 + 可替换角色后端
（含确定性 Mock）+ 最小仿真循环与 JSONL 导出。验收命令为
`uv run python scripts/run_minimal_chain.py` 输出「验收通过」。
技术路线全部由宪章锁定：uv 管理依赖、契约先行、单一胶水层、存储单一入口、
密钥不落代码。`mydocs/` 手册仅作架构参考，代码不照搬。

## Technical Context

**Language/Version**: Python 3.12（uv 管理，`requires-python` 声明）

**Primary Dependencies**: jsonschema（契约校验）、openai + python-dotenv（LLM 接缝模块，
M1 链路不调用）；开发依赖 pytest

**Storage**: SQLite（Python 内置 sqlite3，单文件库）

**Testing**: pytest（契约守卫用例 + 最小链路集成用例）

**Target Platform**: Windows 开发机，命令行脚本（PowerShell / Git Bash 均可执行）

**Project Type**: 单项目 CLI 工具 + 内部库（application 布局，不发布为包）

**Performance Goals**: N/A —— M1 为离线确定性基线，无性能指标

**Constraints**: 全程离线；无 Docker；无 API 密钥可运行；同一输入重复运行产出一致

**Scale/Scope**: 约 10 个源文件；2 张契约；4 张数据表；1 条验收命令

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 本计划的符合性 | 判定 |
|------|----------------|------|
| I. 契约先行 | 先落 `schemas/` 两张 JSON Schema；`store` 入库与导出前强制校验，失败即拒 | PASS |
| II. 单一胶水层 | 第三方库只在 `orchestrator/` 内被 import（jsonschema 于 store，openai/dotenv 于 llm）；scripts 只调 orchestrator | PASS |
| III. 存储单一入口 | `orchestrator/store.py` 为唯一 SQLite 读写点；DDL 幂等 | PASS |
| IV. 适配器隔离与 Mock 基线 | `PersonaBackend` Protocol + 确定性 Mock；`run_minimal_chain.py` 离线可重复 | PASS |
| V. UV 统一依赖 | `uv init` → `pyproject.toml` + `uv.lock` 入库；全部命令经 `uv run` | PASS |
| VI. 密钥与成本边界 | 只提交 `.env.example`；`.env` 已在 `.gitignore`；llm 模块缺密钥时明确报错 | PASS |
| 工作流（一特性一分支） | 当前在 `001-uv-m1-baseline` 分支；spec → plan → tasks → implement 顺序执行 | PASS |

无违规，Complexity Tracking 无需填写。

## Project Structure

### Documentation (this feature)

```text
specs/001-uv-m1-baseline/
├── plan.md              # 本文件
├── research.md          # Phase 0 输出
├── data-model.md        # Phase 1 输出
├── quickstart.md        # Phase 1 输出
├── contracts/           # Phase 1 输出（契约说明 + CLI 契约）
└── tasks.md             # Phase 2 输出（/skill:speckit-tasks，非本命令产物）
```

### Source Code (repository root)

```text
schemas/
├── asset.schema.json        # 资产契约（按手册 3.1 字段口径重新编写）
└── event.schema.json        # 事件契约（按手册 3.2 字段口径重新编写）

db/
└── init_db.py               # SQLite 幂等建表：assets / worlds / runs / events

orchestrator/
├── __init__.py
├── store.py                 # 唯一存储入口 + 契约校验（原则 III）
├── persona.py               # PersonaBackend Protocol + MockPersonaBackend
├── simulation.py            # 最小仿真循环 + JSONL 导出
└── llm.py                   # LLM 统一接缝（M1 链路不调用；缺密钥明确报错）

scripts/
└── run_minimal_chain.py     # M1 验收入口

tests/
├── contract/
│   └── test_schema_guard.py # FR-006 契约守卫：非法资产/事件被拒
└── integration/
    └── test_minimal_chain.py # FR-008 全链路 + FR-010 离线 + 确定性

exports/                     # 事件流产物（已 gitignore）
.env.example                 # 密钥与模型路由模板
pyproject.toml / uv.lock     # uv 项目定义与锁文件
README.md                    # 三步上手
```

**Structure Decision**: 采用单项目 application 布局（非 src-layout、不打包发布），
顶层包 `orchestrator/` 承载全部胶水代码，与宪章原则 II/III 的接缝位置一一对应；
`schemas/` 与 `db/` 独立成目录以体现"契约先行"。手册目标结构（第 7 节）作为参考，
差异仅为新增 `tests/`（宪章要求 M1 可回归）与 uv 工程文件。

## Complexity Tracking

无 —— Constitution Check 全部通过，无需论证的违规项。
