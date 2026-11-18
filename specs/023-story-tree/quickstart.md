# Quickstart: 故事时间树

## 抽取与自查（不需要人工复核）

```bash
uv run narrative timeline import T001 --story story.txt
uv run narrative timeline show T001
```

import 输出自查报告：`schema / source_span / order / dedup` 四项全过、`status: ready`、`node_count`。构造一个 `source_span.quote` 与原文不符的故事，确认 import 自动重试后非零退出且不写库。

## 按树推进四阶段

```bash
uv run narrative timeline drive T001 --stage research
uv run narrative timeline drive T001 --stage world --world-id W001
uv run narrative timeline drive T001 --stage run --run-id R001 --ticks 6 --backend mock
uv run narrative timeline export T001 --out exports/T001-tree.json
uv run narrative export R001 --out exports/R001.jsonl
```

`research` 复用四层漏斗返回 ledger；`run` 的事件带 `node_id`，导出 JSONL 按 node_id → tick → seq 排序。对未 ready 的树执行 drive 应被拒绝且无副作用。

## MCP

```bash
uv run narrative mcp --transport stdio
```

调用 `import_timeline` / `show_timeline` / `drive_timeline`，确认与 CLI 行为一致且只走 workflows。

## 回归

```bash
uv run pytest -q -m "not real"
uv run python scripts/run_minimal_chain.py
```

M1 末行仍为「验收通过」；现有契约、集成与 MCP 测试不回归。
