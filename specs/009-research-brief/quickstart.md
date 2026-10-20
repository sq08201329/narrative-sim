# Quickstart: 立项调研纲领与原料入库

四种验证形态：离线回归、真机立项全流程、防重复漏斗、原料查证。
前置：gptr-mcp 服务在线（004/005 启动方式）、`DEEPSEEK_API_KEY`、
语义漏斗需嵌入服务在线（不在线降级为精确匹配）。

## 1. 离线回归（FR-008 / SC-004）

```bash
uv run pytest -m "not real"
```

预期：全部通过（001-008 既有 + 009 新增；009 全部 mock 在
chat_json/embed/call_tool 三层 + 真实 SQLite 临时库）。

## 2. 生成清单（US1）

```bash
export GPTR_MCP_URL=<gptr-mcp 地址>
uv run python scripts/research_brief.py --theme "南宋末年临安城里的情报战" \
  --out briefs/yanyu.json
```

预期：生成 `briefs/yanyu.json`，含 world/character/lore 三类条目
（每条含 query，资产类含 asset_type），条数 ≤ 12。
**人工审阅**：直接编辑该 JSON 文件增删改条目。

## 3. 批量执行（US1/US3 / SC-001）

```bash
uv run python scripts/research_brief.py --execute briefs/yanyu.json --db yanyu.db
```

预期：逐条打印状态（stored/deduplicated/reused/cached/merged/attached/failed），
结尾总账；资产类入资产表、素材类与全部原料入 research_materials 表；
单条失败不阻断其余条目。

## 4. 防重复验证（US3-AC3 / SC-003a）

再次执行同一清单（或含同义条目的新清单）：
- 精确相同 query → `cached`；高置信同义 → `reused`（零调研调用）
- 库中查 `research_materials`：原料只增不减

## 5. 原料查证（US2 / SC-002）

```bash
uv run python -c "
from orchestrator.store import Store
s = Store('yanyu.db')
for m in s.get_materials('<asset_id>'):
    print(m['query'], '|', m['retriever'], '|', m['context'][:80])
s.close()"
```

预期：原料记录含查询词、检索腿、原文片段；二次调研同主题后记录数增加。
