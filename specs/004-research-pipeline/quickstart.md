# Quickstart: 自动资产调研管线

四种验证形态：离线回归、真机调研、语义去重、故障隔离。
前置：uv sync 完成、`DEEPSEEK_API_KEY` 在环境变量中。

## 0. 启动外部服务（均在仓库外）

**0a. SearXNG**（CWD 必须是其仓库根）：

```powershell
cd D:\kimicode_repos\projects\my-gpt-research\SearXNGforWindows
.\python\python.exe .\searx\webapp.py   # 或双击 SearXNG for Windows.bat
```

**0b. gptr-mcp 服务端**（一次性搭建 + 每次启动）：

```powershell
cd D:\kimicode_repos\projects\my-gpt-research\gptr-mcp
# 一次性：建 venv，requirements 中的 gpt-researcher 改为本地 fork 路径安装
uv venv .venv
.\.venv\Scripts\pip install fastmcp fastapi uvicorn python-dotenv loguru
.\.venv\Scripts\pip install D:\kimicode_repos\projects\my-gpt-research\gpt-researcher
# 每次启动（环境变量见下）
.\.venv\Scripts\python server.py
```

服务端环境变量：`MCP_TRANSPORT=streamable-http`、`RETRIEVER=searx`、
`SEARX_URL=<你的 SearXNG 地址>`、`FAST_LLM/SMART_LLM/STRATEGIC_LLM=deepseek:deepseek-flash`、
`DEEPSEEK_API_KEY=<密钥>`、`OPENAI_API_KEY=<同密钥，启动硬检查>`、
`SMART_TOKEN_LIMIT=8000`、`STRATEGIC_TOKEN_LIMIT=8000`。

健康检查：`curl http://<gptr-mcp 地址>/health`。
把地址写入本项目环境变量 `GPTR_MCP_URL`（如 `.env`，键位见 `.env.example`）。

## 1. 离线回归（FR-008 / SC-004）

```bash
uv run pytest -m "not real"
```

预期：全部通过（001/002/003 既有 + 004 新增；004 测试全部 mock 在
MCP call_tool / llm / 嵌入三层，不需要任何外部进程）。

## 2. 真机调研（US1 / SC-001）

```bash
uv run python scripts/research_asset.py --query "南宋临安城的酒楼" --type scene
uv run python scripts/research_asset.py --query "宋代游方女医者" --type character
```

预期：退出码 0，打印 asset_id；用 store 查询确认资产契约校验通过、
`provenance.retriever="gptr-mcp(searxng)"`、`historical_context.sources` 非空。
注意：每次 deep_research 会产生 3-5 次 LLM 调用的 token 成本（已知情）。

## 3. 语义去重（US2 / SC-002）

```bash
uv run python scripts/research_asset.py --query "南宋临安的酒家" --type scene
```

预期（嵌入服务在线时）：判定与场景 2 的酒楼资产重复，打印已有 asset_id，
库中该类资产数量不变；输出含去重命中说明。
（嵌入服务离线时：降级为名称精确匹配并输出降级提示。）

## 4. 故障隔离（US3 / SC-003）

停掉 gptr-mcp 服务后重跑场景 2 命令：60 秒内明确报错、退出码非 0、库中零新增。
unset `GPTR_MCP_URL` 再跑：明确提示缺少配置，不尝试连接默认地址。
