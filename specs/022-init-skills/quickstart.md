# Quickstart: 初始化与使用技能分发

## 开发与幂等

```bash
uv run narrative --home .init-check init
uv run narrative --home .init-check init
```

首次创建目录、config.ini、.env 与技能；修改这些文件后再次执行，确认内容不变且状态为 existing。检查技能包含 CLI/MCP、三库、工作流和密钥边界。删除临时目录。

## 冻结与发行包

重建应用后在中文空格 HOME 执行 `NarrativeSim.exe init`，比较技能与开发模板完全一致。检查 ZIP 含 `.env.example` 和技能模板，不含真实 `.env`、数据库、模型或日志。

## 回归

```bash
uv run pytest -q -m "not real"
uv run python scripts/run_minimal_chain.py
uv build
```

全部通过后清理临时 HOME，保留正式 dist 产物。
