# Implementation Plan: 接入 WorldSeed 世界引擎

**Branch**: `006-worldseed-integration` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-worldseed-integration/spec.md`

## Summary

WorldSeed 是被动式世界引擎（源码核实）：agent 外部驱动，耦合面仅
`WorldEngine(config)` + `register_agent` + `perceive`/`submit`/`step_async` 五件套。
本特性新建适配器 `orchestrator/world.py`：从资产库组装 SceneConfig（角色卡含
secret + perception 信息不对称规则 + 机械效果动作集），每回合
`perceive → backend.act → submit → step_async`，visible_state 由引擎感知派生
（FR-003 单一真相源，backend 接口零改动）；契约事件翻译复用 001 的 emit 与
shot_hint 口径；每 tick `save_state()` 经 store.py 写 worlds.state，续跑
`load_state` 恢复。DM 不启用（机械效果动作，R3）。M1/M2 链路代码零改动。
技术细节与机制证据见 [research.md](research.md)。

## Technical Context

**Language/Version**: Python 3.12（uv 管理）
**Primary Dependencies**: 新增 worldseed（本地副本 editable 路径安装，MIT，
`uv add --editable`）；TinyTroupe / llm.py / store.py / embedding.py 复用
**Storage**: SQLite（store.py 仅加 `put_world_state` / `get_world_state` 两方法）
**Testing**: pytest 离线套件（**真实引擎 + MockBackend**，引擎离线可跑无需 LLM）
+ 真机验收（TinyTroupe 后端 + DeepSeek 密钥）
**Target Platform**: Windows 本机开发环境
**Performance Goals**: 与 002 真链路同量级（每回合每角色 1 次 LLM 调用）
**Constraints**: WorldSeed 接触面 100% 在 world.py；DM 不启用；
M1/M2 代码零改动；无硬编码配置
**Scale/Scope**: 1 个适配器模块 + 1 个 CLI + 1 个测试文件 + store 两方法

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 说明 |
|---|---|---|
| I 契约先行 | ✅ | FR-007：不动两张契约；事件翻译复用既有 emit 口径 |
| II 单一胶水层 | ✅ | WorldSeed 接触面集中在 `orchestrator/world.py` |
| III 存储单一入口 | ✅ | worlds.state 经 store.py 新增的两方法读写 |
| IV 适配器隔离 + Mock 基线 | ✅ | 真实引擎 + MockBackend 离线测试，零 LLM 依赖 |
| V UV 依赖管理 | ✅ | `uv add --editable` 本地副本；不装 dm extra |
| VI 密钥与成本边界 | ✅ | 复用既有 DEEPSEEK_*；本特性零新增外部服务 |
| VII 一特性一分支 | ✅ | 当前分支 `006-worldseed-integration` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/006-worldseed-integration/
├── plan.md              # 本文件
├── research.md          # Phase 0：9 项决策（引擎形态/配置/快照/翻译/DM）
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── tasks.md             # Phase 2（/skill:speckit-tasks 产出）
```

### Source Code (repository root)

```text
orchestrator/
├── world.py              # 新增：WorldSeed 适配器（配置组装/世界循环/快照/翻译）
├── simulation.py         # 不改（M1/M2 基线）
├── store.py              # 仅加 put_world_state / get_world_state
└── persona*.py           # 不改（backend 接口零改动）

scripts/
└── run_world_chain.py    # 新增 CLI：--world-id --ticks --db [--resume]

tests/contract/
└── test_world_engine.py  # 新增：真实引擎 + MockBackend 离线测试
```

**Structure Decision**: 适配器独立成模块（原则 II），世界循环与 001 的
simulation.py 并存——旧链路是回归基线，新链路是演进主线，两者经
backend 接口共享角色后端。

## Complexity Tracking

无（Constitution Check 全过）。

## 风险备忘

- **worldseed editable 安装**：硬依赖含 fastapi/uvicorn/anthropic（无谓重量），
  uv 解析冲突风险低但 tasks 首个任务即安装验证
- **SceneConfig 组装细节**：entities/agents/actions/perception 四段的字段
  口径以 configs/SCENE_CONFIG.md 与 teahouse.yaml 为准，实施时照模板生成，
  首个里程碑是"组装的配置能过引擎校验并 step"
- **快照格式**：save_state/load_state 的参数形态（entities/tick/characters）
  以 world.py:635-660 实测为准，tasks 含快照续跑专项测试
