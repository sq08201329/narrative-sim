# narrative-sim · 叙事仿真系统

多角色叙事仿真：自动资产调研 → 持久化世界 → 角色心智仿真 → 标准化剧情事件流（JSONL）→ 视频管线。

治理约束见 [.specify/memory/constitution.md](.specify/memory/constitution.md)；
实现细节参考 [mydocs/叙事仿真系统开发手册.md](mydocs/叙事仿真系统开发手册.md)（仅参考，冲突以宪章为准）。

## 三步上手

```bash
uv sync                                    # 1. 安装依赖（读 uv.lock，生成 .venv）
cp .env.example .env                       # 2. 准备环境变量（M1 无需填值）
uv run python scripts/run_minimal_chain.py # 3. 跑最小链路，末行输出「验收通过」
```

M1 全程离线、无需密钥（Mock 角色后端）。运行测试：

```bash
uv run pytest -q    # 标注 real 的用例在无密钥时自动跳过
```

## 真后端链路（M2，TinyTroupe）

1. 在 `.env` 填入 `OPENAI_API_KEY` 与 `OPENAI_BASE_URL`（或 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`，由后端桥接）
2. **cwd 必须是项目根目录**（TinyTroupe 读 `./config.ini`，读不到会静默用包内默认模型）
3. 运行：

```bash
uv run python scripts/run_real_chain.py
```

末行输出「验收通过」，token 用量写入 `runs.token_cost` 可查。
`config.ini` 控制着动作质量校验与并发，勿删。

## 目录结构

```text
schemas/          # 资产 / 事件两张数据契约（唯一接缝，宪章原则 I）
db/               # SQLite 幂等初始化
orchestrator/     # 唯一胶水层：store（唯一写库入口）/ persona / simulation / llm 接缝
scripts/          # run_minimal_chain.py —— M1 回归基线（任何改动后必须不回归）
tests/            # contract/（契约守卫、单通路）+ integration/（链路、后端替换）
exports/          # 事件流产物（gitignore）
```

## 约束速记

- 依赖只经 uv 管理（`uv add` / `uv sync` / `uv run`），禁止裸 `pip`
- 密钥只在 `.env`（已 gitignore），代码里不得出现
- 外部库之间禁止直接 import；数据库读写只经 `orchestrator/store.py`
- 一个特性一个分支，spec → plan → tasks → implement
