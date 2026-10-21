# Phase 0 Research: 立项调研纲领与原料入库

日期：2026-10-21。全部接缝为既有代码事实（research.py / store.py /
embedding.py / llm.chat_json），无外部调研需求。

## R1: 模块划分 — 新增 orchestrator/brief.py（策划层）

**Decision**: 立项生成与批量执行放新模块 `orchestrator/brief.py`，
`research.py` 保持"单条调研"职责不动。

**Rationale**: brief 是调研管线上游的策划层（题材→清单→批量编排），
与 research.py 的"检索栈接触面"是两种职责；分层后研究适配器不膨胀，
立项逻辑可独立测试。brief.py 对资产类条目**调用** research.py 的
`research_asset()`（FR-003 复用，不写第二套），对素材类条目调用
research.py 新增的 `research_material()`（R2）。

## R2: 素材类执行路径 — research.py 加 research_material()

**Decision**: `research_material(query, store, *, link_asset_id=None,
call_tool=None) -> int`：deep_research 取 context → 截断 →
`store.put_material(...)` 返回原料行 id。不做资产化、不做契约校验（FR-004）。

**link 口径**: 素材条目可声明 `link`（asset_id）；未声明时经 FR-011 的
库内匹配找最相关资产挂载；都不沾边时挂字符串 `lore:<题材 slug>`
（asset_id 为 TEXT 无外键，可承载）。

**单发 CLI 同步**: `research_asset()` 内嵌原料持久化——成功后对新资产、
去重命中后对已有资产，均 `put_material(asset_id, query, retriever_label,
context)`（FR-005 覆盖"每次调研"）。截断上限
`RESEARCH_MATERIAL_MAX_CHARS`（默认 8000）。

## R3: 原料表与 store 接口（原则 III）

```sql
CREATE TABLE IF NOT EXISTS research_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT NOT NULL, query TEXT NOT NULL,
    retriever TEXT NOT NULL, context TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_materials_asset ON research_materials(asset_id);
CREATE INDEX IF NOT EXISTS idx_materials_query ON research_materials(query);
```

DDL 进 `db/init_db.py`（幂等，既有库自动补表）。store.py 加三方法：
`put_material(asset_id, query, retriever, context) -> int`、
`get_materials(asset_id) -> list[dict]`、
`get_material_by_query(query) -> dict | None`（精确缓存用，取最新一条）。

## R4: 四层漏斗实现（FR-009~011）

```
条目 query
  ① get_material_by_query(query) 命中 → status="cached"，零调用
  ②（清单生成后）条目两两嵌入了并 ≥ 0.88 → 合并，ledger 记 "merged"
  ③ embed(query) vs 库中资产 name+appearance（embedding.embed_texts）：
     cos ≥ RESEARCH_SKIP_THRESHOLD(0.88) → status="reused"，零调用
     0.80 ≤ cos < 0.88 → 照常调研，素材/原料挂命中资产（"attach"）
  ④ 未命中 → 正常全流程
```

- 嵌入复用 `orchestrator/embedding.py` 的 `embed_texts`；
  不可用（未配置/失败返 None）→ 降级为名称精确匹配（与 004 同语义）
- 资产比较文本与 004 去重一致：`name + appearance.description/visual_prompt`
- ③的跳过判定只用在"资产类"条目；素材类条目即使命中也照常调研
  （剧情素材的价值就是新材料本身），仅把 link 指向命中资产

## R5: 清单形态与审阅（异步文件，spec Assumptions）

```json
{"theme": "南宋末年临安城里的情报战",
 "generated_at": "...", 
 "items": [{"category": "world|character|lore",
            "query": "...", "asset_type": "scene|character|prop|epoch|null"}]}
```

- CLI：`scripts/research_brief.py --theme "..." --out briefs/x.json`（只生成）；
  人改文件后 `--execute briefs/x.json`（批量执行）
- 生成：chat_json 一次调用（题材→三类清单），漂移重试 1 次后明确失败（FR 边界）
- 闸门：`BRIEF_MAX_ITEMS`（默认 12），超出截断并提示
- 每类至少 1 条（生成 prompt 约束 + 生成后校验）

## R6: 总账（FR-006）

执行返回并打印 ledger：`[{query, category, status, asset_id?, reason?}]`，
status ∈ `stored | deduplicated | reused | cached | merged | attached | failed`；
结尾汇总行（各状态计数）。单条 try/except 记录失败继续（FR-007）。

## R7: 环境变量

| 变量 | 含义 | 默认 |
|---|---|---|
| `BRIEF_MAX_ITEMS` | 清单条数闸门 | `12` |
| `RESEARCH_SKIP_THRESHOLD` | 复用跳过阈值 | `0.88` |
| `RESEARCH_ATTACH_THRESHOLD` | attach 区间下限 | `0.80` |
| `RESEARCH_MATERIAL_MAX_CHARS` | 原料截断 | `8000` |

复用：GPTR_MCP_URL / EMBEDDING_* / DEEPSEEK_*。键位进 .env.example。

## R8: 测试策略

离线（全部 mock 接缝，零外部进程）：
- 生成：mock chat_json（正常/漂移重试/三类校验/闸门截断）
- 漏斗①②③：mock embed_texts 与材料表（缓存命中/合并/复用/attach/降级）
- 执行：mock research_asset 与 call_tool（成功/失败不阻断/总账正确）
- 原料表：真实 SQLite（tmp_path）写读/追加/按查询取最新
真机：一个题材全流程（生成→执行→资产与原料查证）+ 同义复跑验证复用标记。

## R9: 依赖与回归面

- 零新增依赖；既有文件改动：store.py（+3 方法）、init_db.py（+DDL）、
  research.py（+research_material、research_asset 内嵌原料持久化）
- research_asset 的行为变化仅是"多写一张表"，004 既有测试需相应确认
  （put_material 在无表旧库上？—— init_db 幂等建表，测试均走 init_db，无碍）
- M1-M5/008 回归由既有 111 项 + 新增用例兜底
