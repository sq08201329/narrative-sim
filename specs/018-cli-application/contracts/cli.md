# CLI Contract

## 通用约定

```text
narrative [--home PATH] [--db PATH] [--library-db PATH] COMMAND ...
```

- 显式参数优先于 `NARRATIVE_HOME` / `NARRATIVE_DB` / `LIBRARY_DB`，未配置时使用数据模型中的默认值。
- `research` 只写调研主库；世界、仿真和导出只写 `--db` 指定的剧目库。
- 除 `mcp` 外，成功时 stdout 输出一个 UTF-8 JSON 对象，stderr 输出诊断；失败不输出成功 JSON。
- 退出码：`0` 成功，`1` 业务或服务失败，`2` 参数错误。
- `status` 在所有服务 ready 时为 0，否则为 1；重复 `stop` 为 0。
- 密钥只从既有环境或 `.env` 获取，不提供密钥命令行参数。

## 服务管理

```text
narrative start
narrative stop
narrative restart
narrative status
```

返回 `action`、`database` 和 `services`。`start` 可复用健康的 external 服务；`stop` 只停止 managed 服务并跳过 external 服务。

## 资产调研

```text
narrative research QUERY --type character|prop|scene|epoch
```

成功返回：

```json
{"asset_id":"char_...","deduplicated":false}
```

## 世界创建

```text
narrative world create WORLD_ID --characters ID1,ID2 --location SCENE_ID [--reset] [--memory-from RUN_ID]
```

成功返回 `world_id`、`characters`、`location`、`action_count`、`revision_pins`、`memory_from`，语义与现有 `create_world` MCP 工具一致。

## 仿真运行

```text
narrative run WORLD_ID --run-id RUN_ID [--ticks 4]
  [--backend tinytroupe|mock] [--resume] [--dm]
  [--dm-max-calls 50] [--dm-knowledge-chars 2000]
  [--memory-from RUN_ID]
```

成功返回 `run_id`、`event_count`、`ticks`、`cost_tokens`；启用裁决时另含 `dm_calls`、`dm_failed`。

## 事件导出

```text
narrative export RUN_ID --out PATH
```

成功返回：

```json
{"path":"exports/run.jsonl","count":5}
```

不存在的 run 必须失败，不创建空的成功产物。

## MCP

```text
narrative mcp [--transport streamable-http|stdio] [--host $MCP_HOST] [--port $MCP_PORT]
```

前台运行并保持现有 MCP 工具与协议行为；stdout 专用于 MCP，不输出 CLI JSON。启动时继承统一数据库路径。
