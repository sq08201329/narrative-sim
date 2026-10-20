# Quickstart: 接入 WorldSeed 世界引擎

四种验证形态：离线回归（真实引擎+MockBackend）、真机世界链路、
断点续跑、信息不对称核验。
前置：uv sync 完成（worldseed 经 editable 路径安装）、
真机场景需 `DEEPSEEK_API_KEY`。

## 1. 离线回归（FR-006 / SC-004）

```bash
uv run pytest -m "not real"
```

预期：全部通过（001-005 既有 + 006 新增；006 用例用真实 WorldSeed 引擎 +
MockBackend，零 LLM 调用、零外部进程）。

## 2. 真机世界链路（US1 / SC-001）

确保资产库有角色与场景资产（可用 004/005 调研产物，或 002 的
char_su_wanqing / scene_yanyu_teahouse）：

```bash
uv run python scripts/run_world_chain.py --world-id world_yanyu --ticks 4
```

预期：退出码 0；≥5 事件落库、契约校验全过、输出验收通过；
资产组装的世界配置打印（角色/场景/动作数）。

## 3. 断点续跑（US2 / SC-003）

```bash
uv run python scripts/run_world_chain.py --world-id world_yanyu --ticks 3
uv run python scripts/run_world_chain.py --world-id world_yanyu --ticks 2 --resume
```

预期：续跑从第 4 回合开始，事件编号连续、零重复、契约全过；
worlds.state 每回合有快照（可用 store 查询 tick 与状态大小）。

## 4. 信息不对称核验（US1-AC2 / SC-002）

世界配置含 secret 的角色 ≥2 时，用离线探针（tests 内同款）分别取两名角色的
perceive 输出：互相看不到对方 secret 字段，可见状态存在可核验差异。
真机场景中可在角色对白/行动中间接观察（不作硬性断言）。

## 5. 旧链路不回归（US3 / FR-007）

```bash
uv run python scripts/run_minimal_chain.py   # M1 最小链路（Mock 后端）
```

预期：与 001 验收输出一致（Mock 基线行为不变）。
