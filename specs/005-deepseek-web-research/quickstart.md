# Quickstart: DeepSeek Web 调研后端

四种验证形态：离线回归、真机调研（零常驻服务）、双后端切换、故障语义。
前置：`DEEPSEEK_API_KEY` 在环境变量中（Search/Fetch 按次计费，
单次调研 = 1 Search + ≤3 Fetch，成本可忽略）。

## 1. 离线回归（FR-007 / SC-004）

```bash
uv run pytest -m "not real"
```

预期：全部通过（001-004 既有 + 005 新增；005 用例全部 mock 在 httpx 层，
不需要任何真实 API）。

## 2. 真机调研 — DeepSeek 后端（US1 / SC-001）

不启动任何外部服务：

```bash
export RESEARCH_BACKEND=deepseek   # 或不设（默认即 deepseek）
uv run python scripts/research_asset.py --query "南宋临安城的酒楼" --type scene
uv run python scripts/research_asset.py --query "宋代游方女医者" --type character
```

预期：退出码 0，打印 asset_id；资产契约校验通过、
`provenance.retriever="deepseek(search+fetch)"`、`historical_context.sources` 非空。

## 3. 双后端切换（US2 / SC-002）

启动 004 的 gptr-mcp + SearXNG（见 004 quickstart 0 节），然后：

```bash
export RESEARCH_BACKEND=gptr-mcp GPTR_MCP_URL=<gptr-mcp 地址>
uv run python scripts/research_asset.py --query "北宋汴梁的茶肆" --type scene
```

预期：两个后端产出契约形态一致，retriever 各自标识
（`deepseek(search+fetch)` / `gptr-mcp(searxng)`）；004 离线测试保持绿。

## 4. 故障语义（US3 / SC-003）

```bash
# 无结果查询：明确"无来源"失败，零写入（官方此情形不计费）
uv run python scripts/research_asset.py --query "zzz 不存在的事物 qqq" --type prop
# DEEPSEEK_API_KEY 故意置错：401 明确报错、不重试、快速失败
```

预期：均退出码非 0、错误信息指明原因、库中零新增。
429 退避与 402 余额场景由离线 mock 覆盖（真机难以稳定复现）。
