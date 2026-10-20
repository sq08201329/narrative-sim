# Quickstart: MCP Server 协议封装

三种验证形态：离线全链（进程内客户端）、真机服务、错误语义。
前置：uv sync 完成；真机场景需 `DEEPSEEK_API_KEY`。

## 1. 离线回归（FR-007 / SC-003）

```bash
uv run pytest -m "not real"
```

预期：全部通过（001-006 既有 + 007 新增；007 用例为 fastmcp 进程内客户端
+ 真实引擎/Mock 基线，零网络零外部进程）。

## 2. 启动服务（FR-003）

```bash
uv run python scripts/run_mcp_server.py
# 默认 streamable-http，127.0.0.1:8300；环境变量可改：
#   MCP_TRANSPORT / MCP_HOST / MCP_PORT
```

健康检查：客户端 `list_tools` 可见六个工具。
注意：启动不要求 gptr-mcp/嵌入服务在线；调研类工具调用时才按各自口径
报错或降级。

## 3. 真机全链（US1 / SC-001）

以 MCP 客户端（Kimi/Claude 或 fastmcp Client）连接 `http://127.0.0.1:8300/mcp`，
依次调用（每步返回携带下一步所需标识）：

```python
await session.call_tool("research_asset",
    {"query": "南宋临安城的酒楼", "asset_type": "scene"})
await session.call_tool("create_world",
    {"world_id": "world_demo", "character_ids": ["char_su_wanqing", "char_shen_ke"],
     "location_id": "scene_yanyu_teahouse"})
await session.call_tool("run_simulation",
    {"world_id": "world_demo", "run_id": "run_demo", "ticks": 2, "backend": "mock"})
await session.call_tool("export_events",
    {"run_id": "run_demo", "out_path": "exports/mcp_demo.jsonl"})
```

预期：各步返回结构化结果；事件契约校验通过；导出文件生成。
真后端（默认 backend）每 tick 每角色约 15-30s，客户端超时按
`120s + 60s × ticks` 配置。

## 4. 错误语义（US2 / SC-002）

- 空 query 调 research_asset → 参数错误（无外部调用）
- 不存在的 world_id 调 run_simulation → 世界不存在/无快照错误
- 停掉 gptr-mcp 调 research_asset → 调研服务故障说明（同 CLI 口径）
- web_fetch 不可抓取 URL → 可读失败说明

server 进程在以上全部场景后仍可正常服务。
