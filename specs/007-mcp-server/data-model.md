# Data Model: MCP Server 协议封装

本特性不改资产/事件契约（FR-006）。以下为协议层数据形态。

## 工具签名与返回（fastmcp 经类型标注自动生成 schema）

| 工具 | 参数 | 返回 |
|---|---|---|
| research_asset | `query: str, asset_type: str` | `{asset_id, deduplicated: bool}` |
| create_world | `world_id: str, character_ids: list[str], location_id: str, reset: bool=False` | `{world_id, characters, location, action_count}` |
| run_simulation | `world_id: str, run_id: str, ticks: int, backend: str="tinytroupe", resume: bool=False` | `{run_id, event_count, ticks, cost_tokens}` |
| export_events | `run_id: str, out_path: str` | `{path, count}` |
| web_search | `query: str, count: int=8` | `{results: [{title, url, summary}]}` |
| web_fetch | `url: str` | `{title, content}` |

backend 取值 `tinytroupe`（默认，真后端）/ `mock`（测试演示）。
所有失败经 ToolError：message = `{错误类型}: {可读原因}`，无堆栈。

## 世界定义（worlds.config 列启用，JSON 文本）

```json
{"character_ids": ["char_a", "char_b"], "location_id": "scene_x"}
```

create_world 写入（build_scene_config 预检资产齐全后）；
run_simulation 读取并调 006 `run_world()`。
重复 world_id 且 `reset=False` → ToolError 拒绝；`reset=True` 覆盖重写。

## 调用链衔接（SC-001 全链形态）

```
research_asset → asset_id（入 character_ids）
create_world   → world_id（worlds.config 登记）
run_simulation → run_id + event_count（worlds.state 快照随写）
export_events  → out_path + count
```
