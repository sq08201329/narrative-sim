# Quickstart: 可迁移运行时

## 干净副本

创建临时副本时排除 `.git`、`.env`、`.venv`、数据库、日志、模型、缓存和导出产物。目录名必须包含中文和空格，且不得包含历史 WorldSeed/gptr-mcp 目录结构。

```bash
uv sync
uv run narrative --help
uv run python scripts/run_minimal_chain.py --db .check/m1.db --out .check/m1.jsonl
uv run pytest -q -m "not real"
```

预期：无固定本机路径解析错误，M1 输出“验收通过”，离线测试全通过。

## 数据路径

在副本中指定临时 HOME，使用 Mock 或替身完成调研、古籍检索、建世界和仿真。预期未覆盖时分别生成/读取：

```text
<HOME>/data/projects/linan.db
<HOME>/data/library.db
<HOME>/data/corpus.db
```

逐个设置 `NARRATIVE_DB`、`LIBRARY_DB`、`CORPUS_DB`，确认只有对应数据库改变。检查旧库哈希或内容，确认未发生自动迁移。

## 外部资源失败与恢复

1. 停止真实服务，将 `LITERT_LM` 指向不存在的程序，启动应指出该配置。
2. 使用可控 LiteRT 替身，模型未导入且 `EMBEDDING_MODEL_FILE` 不存在时，应指出模型文件配置。
3. 提供伪模型文件并验证导入命令被调用；恢复真实配置后执行 `uv run narrative status`。
4. 确认以上失败不影响 M1。

## 来源与卫生

检查 `packages/worldseed` 和 `packages/gptr-mcp` 的上游 commit、MIT LICENSE 与本地修改记录；确认仓库不包含模型、数据库、`.env`、虚拟环境或外部服务日志。
