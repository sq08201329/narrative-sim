# Quickstart: GPT-Researcher 接入 DeepSeek 检索腿

四种验证形态：离线回归、插件安装 spike、真机调研（SearXNG 停开）、
全链路去重（关闭 004 T017）。
前置：`DEEPSEEK_API_KEY` 在环境变量中；gptr-mcp venv 已搭建
（见 004 quickstart 0b）。

## 1. 离线回归（FR-008 / SC-004）

```bash
uv run pytest -m "not real"
```

预期：全部通过（001-004 既有 + 005 插件测试；全部 mock 在 HTTP 层）。

## 2. 插件安装 spike（一次性）

```powershell
cd D:\kimicode_repos\projects\my-gpt-research\gptr-mcp
.\.venv\Scripts\pip install D:\kimicode_repos\projects\narrative-sim\plugins\gptr-deepseek-retriever
```

验证加载：启动服务时 `RETRIEVER=deepseek` 不再报 unknown retriever。

## 3. 启动 gptr-mcp（DeepSeek 检索腿，不启动 SearXNG）

环境变量同 004 quickstart 0b，两处变化：

```powershell
$env:RETRIEVER="deepseek"          # 原为 searx；SEARX_URL 可不设
$env:GPTR_MCP_RETRIEVER_LABEL="gptr-mcp(deepseek-search)"   # 客户端溯源标签（也可不设，默认即此值）
```

健康检查：`curl http://<gptr-mcp 地址>/health`。

## 4. 真机调研（US1 / SC-001）

```bash
export GPTR_MCP_URL=<gptr-mcp 地址>
uv run python scripts/research_asset.py --query "南宋临安城的酒楼" --type scene --db research005.db
uv run python scripts/research_asset.py --query "宋代游方女医者" --type character --db research005.db
```

预期：退出码 0；资产契约校验通过、
`provenance.retriever="gptr-mcp(deepseek-search)"`、sources 非空；
服务端日志可见 DeepSeek Search 调用且无 BeautifulSoup 抓取轮
（content 全文直通）。

## 5. 全链路同义去重（SC-002，关闭 004 T017）

```bash
export EMBEDDING_API_BASE=<嵌入服务地址>
uv run python scripts/research_asset.py --query "南宋临安的酒家" --type scene --db research005.db
```

预期：命中场景 4 的已有资产，返回相同 asset_id，库中 scene 数量为 1。

## 6. 工具函数直调（FR-009，可选）

```bash
uv run python -c "
from gptr_deepseek_retriever import web_search, web_fetch
print(web_search('南宋 临安 酒楼', count=3)[0]['url'])
print(web_fetch('https://example.com') )
"
```

## 7. 切回 searx 腿（US2，可选）

`RETRIEVER=searx` + `SEARX_URL=<地址>` 重启服务（SearXNG 需在线），
`GPTR_MCP_RETRIEVER_LABEL=gptr-mcp(searxng)`，004 路径行为不变。
