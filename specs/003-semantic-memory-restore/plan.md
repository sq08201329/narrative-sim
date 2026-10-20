# Implementation Plan: 恢复语义记忆（本地嵌入服务接入）

**Branch**: `003-semantic-memory-restore` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-semantic-memory-restore/spec.md`

## Summary

撤掉 002 的语义记忆降级（LocalSemanticMemory），把 TinyTroupe 的嵌入通道接到本地
litert-lm 服务（eg2-text-270m，OpenAI 兼容 `/v1/embeddings`）：适配器内子类化
llama-index `OpenAIEmbedding`（`model_name=` 绕白名单、补任务前缀、全异常拦截回零向量、
10s 超时），import tinytroupe 后覆盖 `Settings.embed_model`；后端构造时做可达性+模型身份
预检，失败自动回退 002 降级行为并输出提示。全部改动在适配器模块内，不动两张契约，
无新增依赖。技术细节与实测证据见 [research.md](research.md)。

## Technical Context

**Language/Version**: Python 3.12（uv 管理）
**Primary Dependencies**: TinyTroupe 0.7.0（pin commit）、llama-index-embeddings-openai 0.1.11、
httpx（均已在 lock 中，无新增）
**Storage**: SQLite（既有 store.py，本特性不改存储）
**Testing**: pytest（离线套件）+ 召回探针脚本（在线，不调 LLM）+ 真链路验收（需 DeepSeek 密钥）
**Target Platform**: Windows 本机开发环境
**Performance Goals**: 单次嵌入调用 ≤10s 超时即降级（SC-003）；嵌入不阻塞仿真节奏
**Constraints**: 嵌入代码 100% 在适配器内；服务地址零硬编码；服务离线时仿真 100% 完成
**Scale/Scope**: 单文件改动为主（orchestrator/persona_tinytroupe.py），
外加 .env.example、真链路脚本降级提示、探针脚本扩展、测试

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 说明 |
|---|---|---|
| I 契约先行 | ✅ | FR-006：不动资产/事件契约 |
| II 单一胶水层 | ✅ | FR-008：嵌入接入代码全部在 `orchestrator/persona_tinytroupe.py` |
| III 存储单一入口 | ✅ | 不触碰 store.py；语义记忆在 TinyTroupe 进程内，不入库 |
| IV 适配器隔离 + Mock 基线 | ✅ | MockBackend 与注入 person_cls 路径不触碰嵌入逻辑 |
| V UV 依赖管理 | ✅ | 无新增依赖（llama-index/httpx 已在 lock） |
| VI 密钥与成本边界 | ✅ | 地址/模型/超时走环境变量；.env.example 加键；litert-lm 不入库（FR-007） |
| VII 一特性一分支 | ✅ | 当前分支 `003-semantic-memory-restore` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/003-semantic-memory-restore/
├── plan.md              # 本文件
├── research.md          # Phase 0：7 项决策，全部实测
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── tasks.md             # Phase 2（/skill:speckit-tasks 产出）
```

### Source Code (repository root)

```text
orchestrator/
└── persona_tinytroupe.py   # 唯一改动核心：嵌入子类、预检、降级接线、Settings.embed_model 覆盖

scripts/
├── probe_embedding_service.py  # 扩展为完整召回探针（US1-AC2 验收，不调 LLM）
└── run_real_chain.py           # 打印 semantic_mode（真实/降级及原因）

tests/
└── unit/（或既有布局）
    └── test_persona_tinytroupe_embedding.py  # 离线：预检判定、降级回退、
                                              # 前缀/空文本/截断/超时拦截（mock httpx 层）

.env.example                # 加 EMBEDDING_API_BASE / EMBEDDING_MODEL /
                            # EMBEDDING_TIMEOUT_S / EMBEDDING_MAX_CHARS 键位
```

**Structure Decision**: 单项目布局沿用 001/002 既有结构；本特性不新建包，
所有新逻辑进适配器模块与其离线测试（原则 II/IV）。

## Complexity Tracking

无（Constitution Check 全过）。
