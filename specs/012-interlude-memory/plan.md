# Implementation Plan: 幕间记忆传递

**Branch**: `012-interlude-memory` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-interlude-memory/spec.md`

## Summary

让上一幕的已发生事件以"按角色可感知过滤"的记忆注入下一幕。新增
`orchestrator/interlude.py`（过滤 + 双通道摘要 + 幂等落库）与
`interlude_memories` 表；注入走两路——引擎侧角色卡加 `memory` 键
（WorldSeed AgentConfig.character 自由字段），后端侧 PersonaBackend 新增
`seed_memory` 接缝（TinyTroupe 经 episodic_memory.store，Mock 记录供断言）。
过滤规则复用契约事件：inner_voice 仅本人、可选 visible_to 扩展字段限列内、
其余公开。MCP 加生成/读取工具，create_world/run_simulation/reshoot 加
`memory_from` 参数。

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: 零新增（LLM 通道走 009 既有 chat_json 接缝口径；
TinyTroupe/WorldSeed 既定）

**Storage**: SQLite 经 store.py；新增 `interlude_memories` 表

**Testing**: pytest 离线契约测试（模板通道 + spy/mock 接缝），真机标 real

**Target Platform**: Windows 本机 + MCP streamable-http

**Project Type**: cli/library + MCP server

**Performance Goals**: 非性能特性；LLM 通道每角色一次调用，幂等复用零重复

**Constraints**: 私语/内心零泄漏（SC-001）；不启用时行为逐键一致

**Scale/Scope**: 单库多 world（幕），事件十级~百级，角色个位数

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 依据 |
|------|------|------|
| I. 契约先行 | PASS | contracts/interlude.md 先行；事件过滤用 schema 允许的扩展字段，
不动 001 枚举 |
| II. 单一胶水层 | PASS | 新逻辑全在 orchestrator/interlude.py；worldseed/tinytroupe
接触点仍只在既有接缝文件 |
| III. 存储单一入口 | PASS | interlude_memories 读写全经 store.py |
| IV. 适配器隔离与 Mock 基线 | PASS | 模板通道 + spy 后端离线全覆盖；LLM 通道 real 标记 |
| V. UV 统一依赖 | PASS | 零新增包 |
| VI. 密钥与成本边界 | PASS | LLM 通道按角色一次调用；幂等复用不重复计费；
token 落库 |
| VII. 一特性一分支 | PASS | 012-interlude-memory |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/012-interlude-memory/
├── plan.md              # 本文件
├── research.md          # Phase 0：注入点/过滤口径/幂等等 6 项决策
├── data-model.md        # Phase 1：interlude_memories 表 + 过滤规则
├── quickstart.md        # Phase 1：离线验证 + 真机两幕连跑
├── contracts/
│   └── interlude.md     # Phase 1：生成/读取/注入契约 + MCP 工具签名
└── tasks.md             # /skill:speckit-tasks 产出
```

### Source Code (repository root)

```text
orchestrator/
├── interlude.py         # 新增：可见性过滤 + 双通道摘要 + 幂等落库
├── store.py             # 修改：interlude_memories 原语
├── world.py             # 修改：build_scene_config/run_world 加 memory_from
├── persona.py           # 修改：PersonaBackend 协议加 seed_memory（Mock 记录）
├── persona_tinytroupe.py# 修改：seed_memory 经 episodic_memory.store
└── mcp_server.py        # 修改：generate/get_interlude_memory + memory_from 参数

db/
└── init_db.py           # 修改：interlude_memories 幂等 DDL

tests/contract/
└── test_interlude.py    # 新增：过滤/双通道/幂等/注入/兼容锚点
```

**Structure Decision**: 单项目布局；新逻辑仅 interlude.py 一个模块。

## 设计要点（Phase 1 摘要）

1. **过滤规则**（research.md R2）：事件 → 角色可见 iff
   `type=="inner_voice"` 则仅 `characters[0]`；`visible_to`（schema 允许的
   扩展字段）存在则仅列内；否则全世界角色。
2. **双通道**（R3）：`channel="template"` 产出确定性条目（"第N回合，你
   说了：…"）；`channel="llm"` 经 chat 接缝生成自然语言摘要，输入预算
   `INTERLUDE_MAX_EVENTS`（默认 50，新近优先）。
3. **幂等**（R4）：(run_id, asset_id) 唯一当前版；已存在且
   regenerate=False 直接返回（tokens=0）；regenerate 或修订走 revision
   递增留痕（同 011 口径，表内自管）。
4. **注入**（R1）：run_world(memory_from=run_id) → 逐角色取记忆 →
   build_scene_config 角色卡加 `memory` 键 + backend.seed_memory(cid, text)。
5. **MCP**：`generate_interlude_memory(run_id, channel, regenerate)` /
   `get_interlude_memory(run_id, asset_id?)`；create_world/run_simulation/
   reshoot 加 `memory_from: str | None`。

## Constitution Check（Phase 1 复审）

契约先行（I）；胶水层未外溢（II）；存储单入口（III）；模板通道离线基线
（IV）；零新依赖（V）；幂等 + token 落库（VI）；分支隔离（VII）。
**全部 PASS。**
