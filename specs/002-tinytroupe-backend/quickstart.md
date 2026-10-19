# Quickstart: TinyTroupe 真后端接入（M2）

## 离线回归（无密钥，CI / 日常开发）

```bash
uv sync
uv run pytest -q                                # 全部用例；real 标记自动 skip
uv run python scripts/run_minimal_chain.py      # M1 基线不回归
```

**期望**：测试全绿（real 用例显示 skipped）；最小链路输出「验收通过」。

## 在线验收（有密钥）

```bash
cp .env.example .env   # 填入 OPENAI_API_KEY / OPENAI_BASE_URL / DEEPSEEK_API_KEY
uv run python scripts/run_real_chain.py
```

**期望**（对应 spec SC-001/SC-004、US1/US3）：

- 末行输出 `验收通过`，`exports/` 生成真后端事件流 JSONL
- 事件 ≥5 条且逐条过契约；第 2 回合起的事件可见承接前序内容（SC-002 抽查）
- 数据库 `runs.token_cost` 出现非零值：
  `uv run python -c "import sqlite3; print(sqlite3.connect('narrative_sim.db').execute('SELECT run_id, token_cost FROM runs').fetchall())"`

## 后端切换对照（US2）

```bash
uv run python scripts/run_minimal_chain.py   # Mock，离线
uv run python scripts/run_real_chain.py      # TinyTroupe，在线
```

两脚本除后端注入外同构（contracts/cli-real-chain.md）。

## 负向验证

```bash
cd .. && uv run --project narrative-sim python narrative-sim/scripts/run_real_chain.py
```

**期望**：cwd 守卫触发，明确报错且退出码非 0，不产生任何事件。
