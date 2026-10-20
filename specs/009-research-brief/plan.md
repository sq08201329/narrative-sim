# Implementation Plan: 立项调研纲领与原料入库

**Branch**: `009-research-brief` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-research-brief/spec.md`

## Summary

新增策划层 `orchestrator/brief.py`：题材 →（chat_json）三类调研清单（世界/人物/
剧情）→ 异步文件审阅 → 批量执行（资产类调既有 `research_asset()`，素材类调新增的
`research_material()`，全程四层防重复漏斗：精确缓存 → 清单内合并 → 库内复用匹配
→ attach 追加）。原料表 `research_materials` 经 init_db 幂等建表、store.py 三方法
读写；`research_asset()` 内嵌原料持久化（成功与去重命中均追加）。零新增依赖、
契约不动。技术细节见 [research.md](research.md)。

## Technical Context

**Language/Version**: Python 3.12（uv 管理）
**Primary Dependencies**: 零新增（research.py / embedding.py / store.py /
llm.chat_json 复用）
**Storage**: SQLite——`research_materials` 新表（init_db 幂等 DDL）+
store.py 三方法（put_material / get_materials / get_material_by_query）
**Testing**: pytest 离线套件（chat_json/embed/call_tool 三层 mock + 真实 SQLite）
+ 真机全流程验收（DeepSeek 密钥 + gptr-mcp 服务）
**Target Platform**: Windows 本机开发环境
**Performance Goals**: 清单条数闸门（默认 12）；批量执行单条失败不阻断
**Constraints**: 资产类执行 100% 复用 research_asset()；原料读写 100% 经 store.py；
契约不动；M1-M5/008 不回归
**Scale/Scope**: 1 个新模块 + 1 个 CLI + 3 处既有文件小改 + 1 个测试文件

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 说明 |
|---|---|---|
| I 契约先行 | ✅ | 资产/事件契约不动；素材类不做资产化（type 枚举不扩列） |
| II 单一胶水层 | ✅ | 检索栈接触面仍只在 research.py；brief.py 是调用方不是第二套 |
| III 存储单一入口 | ✅ | 原料表经 init_db DDL + store.py 三方法 |
| IV 适配器隔离 + Mock 基线 | ✅ | 离线三层 mock + 真实 SQLite，零外部进程 |
| V UV 依赖管理 | ✅ | 零新增依赖 |
| VI 密钥与成本边界 | ✅ | 闸门/阈值/截断全走环境变量；成本总账 |
| VII 一特性一分支 | ✅ | 当前分支 `009-research-brief` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/009-research-brief/
├── plan.md              # 本文件
├── research.md          # Phase 0：9 项决策（模块划分/漏斗/表结构/总账）
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── tasks.md             # Phase 2（/skill:speckit-tasks 产出）
```

### Source Code (repository root)

```text
orchestrator/
├── brief.py              # 新增：立项生成 + 四层漏斗 + 批量执行 + 总账
├── research.py           # 加 research_material()；research_asset() 内嵌原料持久化
├── store.py              # 加 put_material / get_materials / get_material_by_query
└── embedding.py          # 不改（embed_texts 复用）

db/
└── init_db.py            # 加 research_materials 幂等 DDL

scripts/
└── research_brief.py     # 新增 CLI：--theme 生成 / --execute 执行

tests/contract/
├── test_research_brief.py       # 新增：生成/漏斗/执行/总账离线测试
└── test_research_pipeline.py    # 加原料持久化断言（004 行为变化确认）

.env.example            # 加 BRIEF_MAX_ITEMS / RESEARCH_SKIP_THRESHOLD /
                        # RESEARCH_ATTACH_THRESHOLD / RESEARCH_MATERIAL_MAX_CHARS
```

**Structure Decision**: 策划层独立成模块（R1）；检索栈接触面零扩张
（research.py 只是多一个素材入口函数）；存储改动经 init_db + store 惯例。

## Complexity Tracking

无（Constitution Check 全过）。
