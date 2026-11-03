# Path and Runtime Contract

## 路径优先级

1. 显式命令参数（仅 `--home`、`--db`、`--library-db` 已有参数）。
2. 对应环境变量。
3. 本契约默认值。

`NARRATIVE_DB`、`LIBRARY_DB`、`CORPUS_DB` 互不因其中一个被覆盖而改变。`NARRATIVE_HOME` 只影响未被单独覆盖的路径。

## 默认位置

```text
<HOME>/data/projects/linan.db
<HOME>/data/library.db
<HOME>/data/corpus.db
<HOME>/logs/
<HOME>/run/
```

`CORPUS_DB` 为空字符串时视为未配置并使用派生默认值。所有业务库职责与 `data/README.md` 保持一致。

## 服务资源

gptr-mcp 从仓库 `packages/gptr-mcp/server.py` 启动，使用根项目 Python 环境，不读取 `GPTR_ROOT`。

嵌入模型使用 `EMBEDDING_MODEL_FILE`；只有模型尚未导入且文件不存在时，启动才因模型文件失败。已有健康服务仍可复用。

## 兼容性

CLI 命令、MCP 工具、数据库 Schema 和业务结果结构不变。`scripts/start_stack.ps1` 继续接受 `start|stop|restart|status` 与 `DbPath`。
