# Phase 1 Data Model: TinyTroupe 真后端接入（M2）

本特性不新增持久化实体，不改动两张契约 Schema。以下为内部结构与配置模型。

## 内部结构

### 角色心智实例缓存（进程内，不入库）

| 键 | 值 | 生命周期 |
|----|-----|----------|
| `asset_id` | `TinyPerson` 实例 | 一次仿真运行；跨回合复用，记忆留在实例 episodic memory 中 |

约束：实例名 = `asset_id`（规避 TinyPerson 全局注册表重名报错）。

### persona_spec → TinyPerson 字段映射

| 资产字段 | TinyPerson persona 键 |
|----------|----------------------|
| `name` | （作为实例名以外的展示名）`name` |
| `persona_spec.age` | `age` |
| `persona_spec.occupation` | `occupation` |
| `persona_spec.personality` | `personality` |
| `persona_spec.beliefs` | `beliefs` |
| `persona_spec.speech_style` | `style`（prompt 模板强制键） |

### 动作映射（TinyTroupe → 事件契约）

| TinyTroupe 动作 `type` | 事件 `type` | 说明 |
|------------------------|-------------|------|
| `TALK` | `dialogue` | content 原样 |
| `THINK` | `inner_voice` | content 原样 |
| `DONE` | —（丢弃） | 回合结束标记，不产生事件 |

`emotion` 取自 `act(return_actions=True)` 返回的 `cognitive_state.emotions`。

## 存储改动（唯一入口内）

- `Store.update_run_cost(run_id: str, total_tokens: int) -> None`
  更新 `runs.token_cost`（列已存在，001 建表）。读取方为后续里程碑与人工对账。

## 配置模型

### `config.ini`（项目根目录，TinyTroupe 读取 cwd）

| 键 | 值 | 依据 |
|----|----|------|
| `[OpenAI] api_type` | `openai` | 走 OpenAIClient 注册分支 |
| `[OpenAI] model` | `deepseek-flash` | 覆盖包内默认 gpt-5-mini |
| `[ActionGenerator] max_attempts` | `2` | 质量重试次数 |
| `[ActionGenerator] enable_quality_checks` | `True` | 包内默认 False，必须显式开 |
| `[ActionGenerator] continue_on_failure` | `True` | 失败返回最高分候选而非抛异常 |
| `[Simulation] parallel_agent_actions` | `False` | M2 串行，保成本归属正确 |

### `.env` 新增键（模板同步到 `.env.example`）

| 键 | 用途 |
|----|------|
| `OPENAI_API_KEY` | TinyTroupe `OpenAIClient` 直接读取 |
| `OPENAI_BASE_URL` | openai SDK 原生读取，指向 DeepSeek |

## 状态流转

- `Run.status`：`running → done`（真链路成功）/ `failed`（终极失败，已入库事件保留）

## 校验规则

- 事件产出路径不变：`backend.act` → emit → `store.put_event` 契约校验 → 落库；
  解析失败重试耗尽后**不 emit**，抛明确错误
- 真链路启动前置：`OPENAI_API_KEY`、`OPENAI_BASE_URL` 存在且 cwd 为项目根
