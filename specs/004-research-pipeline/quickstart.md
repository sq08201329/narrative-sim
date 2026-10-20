# Quickstart: 自动资产调研管线

四种验证形态：离线回归、真机调研、语义去重、故障隔离。
前置：uv sync 完成、`DEEPSEEK_API_KEY` 在环境变量中、crawl4ai 浏览器已装
（`uv run crawl4ai-setup`，一次性）。

## 0. 启动 SearXNG（仓库外）

在 SearXNGforWindows 仓库根目录启动（CWD 必须是其仓库根）：

```powershell
cd D:\kimicode_repos\projects\my-gpt-research\SearXNGforWindows
.\python\python.exe .\searx\webapp.py   # 或双击 SearXNG for Windows.bat
```

健康检查：`curl http://<searxng 地址>/healthz`。
把地址写入环境变量 `SEARXNG_URL`（如 `.env`，键位见 `.env.example`）。

## 1. 离线回归（FR-008 / SC-004）

```bash
uv run pytest -m "not real"
```

预期：全部通过（001/002/003 既有 + 004 新增；004 测试全部 mock 在
searxng HTTP / crawler / llm 三层，不需要任何外部进程）。

## 2. 真机调研（US1 / SC-001）

```bash
uv run python scripts/research_asset.py --query "南宋临安城的酒楼" --type scene
uv run python scripts/research_asset.py --query "宋代游方女医者" --type character
```

预期：退出码 0，打印 asset_id；用 store 查询确认资产契约校验通过、
`provenance.retriever="searxng+crawl4ai"`、`historical_context.sources` 非空。

## 3. 语义去重（US2 / SC-002）

```bash
uv run python scripts/research_asset.py --query "南宋临安的酒家" --type scene
```

预期（嵌入服务在线时）：判定与场景 2 的酒楼资产重复，打印已有 asset_id，
库中该类资产数量不变；输出含去重命中说明。
（嵌入服务离线时：降级为名称精确匹配并输出降级提示。）

## 4. 故障隔离（US3 / SC-003）

停掉 SearXNG 后重跑场景 2 命令：60 秒内明确报错、退出码非 0、库中零新增。
unset `SEARXNG_URL` 再跑：明确提示缺少配置，不尝试连接默认地址。
