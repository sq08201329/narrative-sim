# Implementation Plan: TinyTroupe 真后端接入（M2）

**Branch**: `002-tinytroupe-backend` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-tinytroupe-backend/spec.md`

## Summary

在宪章原则 IV 的适配器边界内接入 TinyTroupe：新增 `orchestrator/persona_tinytroupe.py`
实现既有 `PersonaBackend` Protocol，`TinyPerson` 实例按 `asset_id` 缓存以保记忆连续；
新增 `scripts/run_real_chain.py` 与最小链路同构、仅替换后端注入；token 用量经
TinyTroupe client 单例统计后按 `run_id` 写入 `runs.token_cost`。
依赖以带 commit 的 git URL 锁入 `pyproject.toml` / `uv.lock`。
关键外部事实全部经本地源码副本核实（见 research.md）：TinyTroupe 的
`OpenAIClient` 不消费 `base_url` 配置，必须经 `OPENAI_BASE_URL` 环境变量走
OpenAI SDK 原生路径接 DeepSeek。

## Technical Context

**Language/Version**: Python 3.12（uv 管理）

**Primary Dependencies**: 新增 `tinytroupe`（git+https，pin commit
`a6244b358a1fe1c71bf751f7ba0f8dfa368ec5a4`，v0.7.0）；既有 jsonschema / openai /
python-dotenv / pytest 不变

**Storage**: SQLite（沿用；`runs.token_cost` 字段已存在，本特性首次写入真实值）

**Testing**: pytest —— 单元测试用 monkeypatch 隔离 LLM（离线可跑，进回归套件）；
真后端验收用例打标 `@pytest.mark.real`，无密钥时 skip

**Target Platform**: Windows 开发机，命令行脚本；真后端需网络访问 DeepSeek

**Project Type**: 单项目 CLI 工具 + 内部库（沿用 001 application 布局）

**Performance Goals**: 单次 4 回合单角色仿真 < 10 分钟（spec SC-001）

**Constraints**: Mock 链路全程离线不变；真后端脚本 cwd 必须是项目根目录；
角色不接 grounding faculty（embedding 地雷）；仿真串行运行（成本统计单例无 run 隔离）

**Scale/Scope**: 新增 1 个适配器模块 + 1 个链路脚本 + 1 个 config.ini + 约 3 个测试文件；
改动 `store.py`（加成本写入）与 `.env.example`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 本计划的符合性 | 判定 |
|------|----------------|------|
| I. 契约先行 | 两张 Schema 零变更；真后端事件走同一 `put_event` 校验，不合格不入库 | PASS |
| II. 单一胶水层 | `tinytroupe` 只在 `orchestrator/persona_tinytroupe.py` 内被 import；scripts 不直接依赖 | PASS |
| III. 存储单一入口 | 成本写入经 `store.update_run_cost()` 新增方法，不开第二通路 | PASS |
| IV. 适配器隔离与 Mock 基线 | 新后端实现同一 Protocol；pin commit `a6244b3`；M1 Mock 链路离线不回归（测试套件不依赖网络） | PASS |
| V. UV 统一依赖 | `uv add "tinytroupe @ git+https://…@a6244b3…"`，锁入 uv.lock | PASS |
| VI. 密钥与成本边界 | `OPENAI_API_KEY` / `OPENAI_BASE_URL` 只进 `.env` / `.env.example`；token 按 run_id 聚合落库 | PASS |
| 工作流 | 分支 `002-tinytroupe-backend`；spec → plan → tasks → implement | PASS |

无违规，Complexity Tracking 无需填写。

## Project Structure

### Documentation (this feature)

```text
specs/002-tinytroupe-backend/
├── plan.md              # 本文件
├── research.md          # Phase 0：TinyTroupe API 调研结论（含源码行号证据）
├── data-model.md        # Phase 1：缓存映射、config.ini 键、成本写入
├── quickstart.md        # Phase 1：离线回归 + 在线验收路径
├── contracts/           # Phase 1：后端协议映射 + 真链路 CLI 契约
└── tasks.md             # Phase 2（/skill:speckit-tasks 产物）
```

### Source Code (repository root)

```text
orchestrator/
├── persona_tinytroupe.py   # 新增：TinyTroupeBackend（PersonaBackend 实现）
└── store.py                # 改动：新增 update_run_cost(run_id, total_tokens)

scripts/
└── run_real_chain.py       # 新增：与 run_minimal_chain.py 同构，仅后端不同

config.ini                  # 新增：TinyTroupe 配置（cwd=项目根时生效）
.env.example                # 改动：补 OPENAI_API_KEY / OPENAI_BASE_URL

tests/
├── contract/
│   └── test_tinytroupe_backend.py    # 动作映射/缓存/成本记账（monkeypatch，离线）
└── integration/
    └── test_real_chain.py            # @pytest.mark.real，无 OPENAI_API_KEY 时 skip
```

**Structure Decision**: 沿用 001 的 application 布局；所有 TinyTroupe 接触面集中在
`orchestrator/persona_tinytroupe.py` 一个文件内（原则 II 的"接缝只有一处"）。

## Complexity Tracking

无 —— Constitution Check 全部通过，无需论证的违规项。
