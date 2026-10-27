# Quickstart: 古籍书目无损修复

## 离线回归

```bash
uv run pytest tests/contract/test_corpus.py -q
uv run pytest -m "not real" -q
uv run python scripts/run_minimal_chain.py
```

预期：全部通过；同名异路径及同内容各有独立记录，指定三段/四段/空作者样例正确。

## 候选库修复（不替换生产库）

```bash
uv run python -X utf8 scripts/corpus_repair.py "D:\课程\来自：分享\206-中华十部古籍藏书11.6亿汉字" --db data/corpus.db
```

预期：生成候选库及 JSON 报告；报告为 13,409 条书目、13,408 条非空、1 条空书，
恢复 11 条，旧块保持校验通过。默认不修改 `data/corpus.db`。

## 应用与验收

确认报告及磁盘空间后，使用一个新的 `--target` 并在同一次迁移命令末尾加
`--apply`；工具会在校验通过后换库并打印唯一回滚路径。候选库禁止覆盖，因此不能对已
存在的候选库重复追加 `--apply`。既有 `data/corpus.db.bak` 不得被覆盖。

```bash
uv run python -X utf8 db/corpus.py stats data/corpus.db
uv run python -X utf8 db/corpus.py search data/corpus.db 茶肆
uv run python -X utf8 db/corpus.py search data/corpus.db 皇城司
```

预期：13,409 部；检索结果书名及篇目正确。重复执行候选修复仍得到一致结果。
