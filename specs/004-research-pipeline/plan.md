# Implementation Plan: 自动资产调研管线

**Branch**: `004-research-pipeline` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-research-pipeline/spec.md`

## Summary

实现"查询词 → 契约资产入库"的自动调研管线：本项目作为 MCP 客户端调用仓库外的
**gptr-mcp 服务**（GPT-Researcher 官方 MCP 封装，独立 venv 进程，检索后端 SearXNG），
`deep_research` 一次调用拿回 context + source_urls → 复用 002 `llm.chat_json()`
按资产契约结构化 → `store.put_asset()` 校验入库；入库前语义嵌入去重
（003 嵌入助手提升到 `orchestrator/embedding.py` 共享，降级为名称精确匹配）。
gpt-researcher 的 140+ 依赖全部隔离在服务端进程外（修订记录见
[research.md](research.md) R2/R3）。本项目 MCP 客户端接触面集中在
`orchestrator/research.py` 一个适配器模块。

## Technical Context

**Language/Version**: Python 3.12（uv 管理）
**Primary Dependencies**: 新增 `mcp`（官方 MCP 客户端包，pin）；
httpx / llm.py / store.py / embedding.py 复用既有；
服务端（仓库外）：gptr-mcp + gpt-researcher 本地 fork + SearXNG
**Storage**: SQLite（store.py 仅加 `list_assets(type)` 读方法）
**Testing**: pytest 离线套件（MCP call_tool / llm / 嵌入三层 mock）
+ 真机验收脚本（需 gptr-mcp 服务 + SearXNG + DeepSeek 密钥）
**Target Platform**: Windows 本机开发环境
**Performance Goals**: 服务不可达时 60s 内明确报错（SC-003）；
deep_research 为长调用，MCP 超时默认 180s
**Constraints**: MCP 接触面 100% 在 research.py；服务地址零硬编码；
失败零部分写入；M1/M2/003 不回归
**Scale/Scope**: 新增 2 个模块 + 1 个 CLI 脚本 + 1 个测试文件；
003 嵌入助手代码搬家（行为不变）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 说明 |
|---|---|---|
| I 契约先行 | ✅ | FR-009：不动资产/事件契约；put_asset schema 校验把关 |
| II 单一胶水层 | ✅ | MCP 接触面集中在 `orchestrator/research.py`；嵌入统一经 `embedding.py` |
| III 存储单一入口 | ✅ | 写入只走 `store.put_asset()`；仅新增只读 `list_assets(type)` |
| IV 适配器隔离 + Mock 基线 | ✅ | 离线测试三层 mock，不依赖任何外部进程 |
| V UV 依赖管理 | ✅ | 仅 `uv add mcp`（pin）；服务端依赖不进本项目 lock |
| VI 密钥与成本边界 | ✅ | GPTR_MCP_URL 等走环境变量；服务端进程在仓库外 |
| VII 一特性一分支 | ✅ | 当前分支 `004-research-pipeline` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/004-research-pipeline/
├── plan.md              # 本文件
├── research.md          # Phase 0：9 项决策 + 风险备忘（含 gptr-mcp 服务端核实）
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── tasks.md             # Phase 2（/skill:speckit-tasks 产出）
```

### Source Code (repository root)

```text
orchestrator/
├── research.py           # 新增：调研管线 + MCP 客户端封装（deep_research 调用）
├── embedding.py          # 新增：003 嵌入助手共享化（自 persona_tinytroupe 搬入）
├── persona_tinytroupe.py # 改为 import embedding.py（行为不变）
├── store.py              # 仅加 list_assets(type) 读方法
└── llm.py                # 不改（chat_json 复用）

scripts/
└── research_asset.py     # 新增 CLI：--query --type --db，打印 asset_id / 明确错误

tests/contract/
└── test_research_pipeline.py  # 新增：三层 mock 的离线测试

.env.example              # 加 GPTR_MCP_URL / RESEARCH_TIMEOUT_S /
                          # RESEARCH_DEDUP_THRESHOLD 键位
```

**Structure Decision**: 单项目布局沿用 001-003 既有结构；调研栈适配器独立成模块
（原则 II），嵌入助手共享化是唯一的跨特性触碰（R5，回归套件兜底）。

## Complexity Tracking

无（Constitution Check 全过）。

## 风险备忘

见 research.md 末节：服务端 venv 搭建（本地 fork 路径安装）为 tasks 首个 spike；
streamable-http 优先、sse 兜底；360search 单引擎由用户按需加开；
deep_research token 成本已知情接受。
