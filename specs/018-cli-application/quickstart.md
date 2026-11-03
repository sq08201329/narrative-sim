# Quickstart: 统一 CLI 应用

## 准备

```bash
uv sync
uv run narrative --help
```

验收使用临时数据目录，不触碰现有真实数据库：

```bash
export NARRATIVE_HOME="$PWD/.cli-check"
export NARRATIVE_DB="$NARRATIVE_HOME/data/projects/check.db"
```

## 离线工作流

1. 从现有最小链路夹具准备角色和场景资产：

   ```bash
   uv run python -c "from db.init_db import init; from orchestrator.store import Store; from scripts.run_minimal_chain import CHARACTER,SCENE; import os; p=os.environ['NARRATIVE_DB']; init(p); s=Store(p); s.put_asset(CHARACTER); s.put_asset(SCENE); s.close()"
   ```

2. 创建世界：

   ```bash
   uv run narrative world create world_cli \
     --characters char_su_wanqing --location scene_yanyu_teahouse
   ```

   预期：JSON 含 `world_id` 和非空 `revision_pins`。

3. 运行并导出：

   ```bash
   uv run narrative run world_cli --run-id run_cli --ticks 4 --backend mock
   uv run narrative export run_cli --out "$NARRATIVE_HOME/exports/run_cli.jsonl"
   ```

   预期：至少 5 条事件，JSON 含正确 `run_id`、`event_count` 与导出 `path`，JSONL 逐条通过现有契约。

4. 错误语义：

   ```bash
   uv run narrative export missing_run --out "$NARRATIVE_HOME/exports/missing.jsonl"
   ```

   预期：退出码 1，stderr 指出 run 不存在，无成功 JSON。

## 服务生命周期

使用测试控制的本地服务验证 `start → status → repeated start → restart → stop → repeated stop`：状态准确、无重复进程，external 服务不会被停止。真实技术栈还需配置 `GPTR_ROOT`、`EMBEDDING_ROOT` 和既有模型/凭据，不在离线验收中强制启动。

## MCP 兼容

```bash
uv run narrative mcp --transport streamable-http --port 8300
```

由现有 FastMCP 客户端连接并列工具，工具数量与既有 `scripts/run_mcp_server.py` 启动结果一致。

## 回归

```bash
uv run pytest -q -m "not real"
uv run python scripts/run_minimal_chain.py --db "$NARRATIVE_HOME/data/m1.db" --out "$NARRATIVE_HOME/exports/m1.jsonl"
```

预期：全部离线测试通过，最小链路末行输出“验收通过”。完成后删除临时 `.cli-check`。
