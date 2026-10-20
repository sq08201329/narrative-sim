# Implementation Plan: DeepSeek Web 调研后端（与 gptr-mcp 并存）

**Branch**: `005-deepseek-web-research` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-deepseek-web-research/spec.md`

## Summary

在既有调研适配器 `orchestrator/research.py` 内增加第二个检索后端：DeepSeek 官方
Search/Fetch API（`{DEEPSEEK_BASE_URL}/v1/tools/search|fetch`，Bearer 复用
`DEEPSEEK_API_KEY`）。后端经 `RESEARCH_BACKEND` 环境变量选择（默认 deepseek），
产出与 deep_research 同形态材料，管线的抽取/去重/入库零改动；
`provenance.retriever` 改由检索层回报（gptr-mcp 路径行为不变）。
成本闸门：1 次 Search + ≤3 次 Fetch/调研；429/408/5xx 退避重试、402 明确报余额。
零新增依赖、零常驻服务。技术细节见 [research.md](research.md)。

## Technical Context

**Language/Version**: Python 3.12（uv 管理）
**Primary Dependencies**: 零新增（httpx / llm.py / store.py / embedding.py 复用）
**Storage**: SQLite（不动）
**Testing**: pytest 离线套件（httpx 层 mock 全场景）+ 真机验收（仅 DeepSeek 密钥，
零常驻服务）
**Target Platform**: Windows 本机开发环境
**Performance Goals**: 单次调研 = 1 Search + ≤3 Fetch（计费可预期）；
重试上限 3 次（2s/4s/8s 退避）
**Constraints**: 检索接入 100% 在 research.py；端点/密钥零新增配置；
gptr-mcp 路径行为不变；M1-M4 不回归
**Scale/Scope**: 单模块改动 + 单测试文件加用例 + .env.example 键位

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 说明 |
|---|---|---|
| I 契约先行 | ✅ | FR-008：不动两张契约；retriever 值经 resp 键回报，schema 不感知 |
| II 单一胶水层 | ✅ | DeepSeek 检索接触面进 `orchestrator/research.py`（调研栈适配器） |
| III 存储单一入口 | ✅ | 写入仍只走 `store.put_asset()` |
| IV 适配器隔离 + Mock 基线 | ✅ | httpx 层 mock 全覆盖，零真实 API 依赖 |
| V UV 依赖管理 | ✅ | 零新增依赖 |
| VI 密钥与成本边界 | ✅ | 端点由 DEEPSEEK_BASE_URL 派生、密钥复用；成本闸门 FR-005 |
| VII 一特性一分支 | ✅ | 当前分支 `005-deepseek-web-research` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/005-deepseek-web-research/
├── plan.md              # 本文件
├── research.md          # Phase 0：8 项决策（API 事实 + 错误/成本口径）
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── tasks.md             # Phase 2（/skill:speckit-tasks 产出）
```

### Source Code (repository root)

```text
orchestrator/
└── research.py           # 改动：DeepSeek 后端工厂（Search/Fetch/退避/成本闸门）
                          # + RESEARCH_BACKEND 选择器 + retriever 键回报
                          # gptr-mcp 路径行为不变（FR-008）

tests/contract/
└── test_research_pipeline.py  # 加用例：Search/Fetch mock、后端选择、
                               # 429/402/无结果、材料组装、retriever 标识

.env.example              # 加 RESEARCH_BACKEND / RESEARCH_DS_COUNT /
                          # RESEARCH_DS_FETCH_MAX / RESEARCH_DS_RETRIES
```

**Structure Decision**: 不新建模块——DeepSeek 检索属调研栈接触面，与 gptr-mcp
后端同住一个适配器（原则 II 的"集中"语义）；004 既有结构不动。

## Complexity Tracking

无（Constitution Check 全过）。
