# Implementation Plan: DM 裁判启用（真实裁决提供者）

**Branch**: `010-dm-adjudicator` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-dm-adjudicator/spec.md`

## Summary

启用真实 DM 裁决，替换当前的 Mock 占位。核心发现：WorldSeed 自带
`LiteLLMDMProvider`（litellm + instructor 结构化输出、错误反馈重试、降级模型、
token 统计）。litellm/instructor 是 worldseed 的 `[dm]` 可选依赖，本特性启用
`worldseed[dm]` 并放宽 openai 钉（>=2,<3.35，见 Technical Context）。工作集中在胶水层：新建 `orchestrator/dm.py` 薄工厂（环境桥接 +
模型选择），`orchestrator/world.py` 增加显式开关（`act` 动作挂裁决配置、
`scene.dm_knowledge` 注入调研原料要点、`max_dm_calls` 成本帽），
`_CaptureRecorder` 捕获引擎 `dm_call` 审计记录经 store.py 落新表 `dm_calls`。
未启用时行为与现状逐字节一致。

## Technical Context

**Language/Version**: Python 3.11（项目既定）

**Primary Dependencies**: worldseed[dm]（editable 本地副本，dm extra 引入
litellm>=1.60 / instructor>=1.7）；openai 钉放宽为 >=2,<3.35（instructor 的
jiter<0.15 与 openai 3.35.1 的 jiter>=0.16 冲突；3.35.1 系脚手架时期顺手钉的
最新版，无实质依据）

**Storage**: SQLite，唯一入口 orchestrator/store.py（新增 `dm_calls` 表 +
`put_dm_call` / `list_dm_calls`）

**Testing**: pytest；离线契约测试为默认集，真机验收标 `@pytest.mark.real`

**Target Platform**: Windows 开发机（Git Bash + pwsh），本地运行

**Project Type**: cli/library（仿真编排器）

**Performance Goals**: 非性能特性；单次裁决超时默认 30s 可配，重试硬上限

**Constraints**: 离线测试零外部调用；未配置密钥时行为与现状一致；裁决成本有
硬上限（`max_dm_calls`）

**Scale/Scope**: 单世界、个位数角色、每 tick 至多每角色一次裁决调用

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 依据 |
|------|------|------|
| I. 契约先行 | PASS | `contracts/dm-provider.md` 先行定义工厂签名、配置键、dm_calls 表契约 |
| II. 单一胶水层 | PASS | WorldSeed 接触面仍全部在 orchestrator/（world.py + 新 dm.py），无第二触点 |
| III. 存储单一入口 | PASS | dm_calls 经 store.py 新方法落库；init_db.py 建表 |
| IV. 适配器隔离与 Mock 基线 | PASS | Mock 仍为默认；真实裁决 opt-in；离线测试不经 LiteLLMDMProvider |
| V. UV 统一依赖 | PASS | 经 uv 启用 worldseed[dm] extra（litellm/instructor），锁文件同步更新 |
| VI. 密钥与成本边界 | PASS | 沿用 DEEPSEEK_*→OPENAI_* 桥接（002 模式）；max_dm_calls 硬帽；逐次审计 token |
| VII. 一特性一分支 | PASS | 当前分支 010-dm-adjudicator |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/010-dm-adjudicator/
├── plan.md              # 本文件
├── research.md          # Phase 0：复用 LiteLLMDMProvider 等 7 项决策
├── data-model.md        # Phase 1：dm_calls 表 + DMOptions 配置对象
├── quickstart.md        # Phase 1：离线验证 + 真机验收步骤
├── contracts/
│   └── dm-provider.md   # Phase 1：工厂/配置/审计契约
└── tasks.md             # /skill:speckit-tasks 产出
```

### Source Code (repository root)

```text
orchestrator/
├── dm.py                # 新增：裁决提供者薄工厂（环境桥接 + LiteLLMDMProvider 构造）
├── world.py             # 修改：DMOptions 开关、act 挂裁决配置、dm_knowledge 注入、
│                        #        dm_provider 透传引擎、_CaptureRecorder 捕获 dm_call
└── store.py             # 修改：put_dm_call / list_dm_calls

db/
└── init_db.py           # 修改：dm_calls 表

scripts/
└── run_world_chain.py   # 修改：--dm / --dm-knowledge-chars / --dm-max-calls 开关

tests/contract/
└── test_dm_adjudicator.py  # 新增：离线契约测试（mock 引擎层验证，零外部调用）
```

**Structure Decision**: 单项目布局，全部改动落在既定 orchestrator 胶水层与
store 单一入口内，不新增顶层目录。

## 设计要点（Phase 1 摘要）

1. **裁决范围**：仅 `act` 动作挂 `DMConfig`（say/whisper 是确定性通讯，无需裁决）。
   `DMConfig.hint` 由场景描述 + 默认值生成；`allowed_ops`/`max_effects` 用引擎默认
   （set/increment/decrement/emit_event，上限 5）。
2. **史料注入**：`build_dm_knowledge(store, asset_ids, budget)` 汇总参与角色与场景
   资产的调研原料（query 作标题 + context 截断），默认预算 2000 字符，超出按条
   截断丢弃尾部；无原料时为空串（引擎原生支持）。
3. **审计**：引擎每次裁决（含失败）调用 `recorder.record("dm_call", ...)`；
   `_CaptureRecorder.record` 捕获后经 `store.put_dm_call` 落库（FR-009）。
4. **降级**：引擎内建重试（error_feedback 回注）+ 失败兜底叙事 + dm_call failed
   记录，本特性只做配置，不重复实现（FR-005）。
5. **环境桥接**：复用 002 模式——仅有 DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL 时映射
   OPENAI_*；模型取 `MODEL_FAST`（默认 deepseek-flash），LiteLLM 模型串为
   `openai/{MODEL_FAST}`（litellm openai provider 读 OPENAI_BASE_URL）。

## Constitution Check（Phase 1 复审）

设计落定后逐条复核：契约文件已先行（I）；WorldSeed 接触面未外溢（II）；
dm_calls 唯一写入点是 store.put_dm_call（III）；Mock 基线与离线测试不受影响
（IV）；`uv lock` 无依赖变更（V）；密钥只经既有环境变量、成本帽与审计齐备
（VI）；全部工作在 010-dm-adjudicator 分支（VII）。**全部 PASS。**
