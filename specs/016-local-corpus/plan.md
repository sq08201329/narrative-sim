# Implementation Plan: 古籍文库（本地语料检索层）

**Branch**: `016-local-corpus` | **Date**: 2026-10-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/016-local-corpus/spec.md`

## Summary

把 1.16 亿字古籍藏书转正为项目检索层。spike（`db/corpus.py`，梦粱录实测）
升级为：`corpus.py` 全量入库（批量 CLI、结构感知分块、元数据补齐、哈希
幂等）+ 检索三件套（关键词/过滤/书目浏览）+ 调研管线古籍腿
（research.py 复用接缝，典籍原文+转写入原料表）+ MCP 双工具 +
DM 史料源扩展 + 命中集嵌入精排（可选，mock 可测）。嵌入实测约束
（480-600ms/块、约 400 字上限）决定：全量嵌入不做，精排只打命中集。
含宪章 III 措辞修正（每存储域单一入口）。

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: 零新增（sqlite3 FTS5 内置；嵌入走 003 既有
OpenAI 兼容服务；LLM 走 orchestrator/llm.py 既有接缝）

**Storage**: `data/corpus.db` 独立共享库，单一入口 `db/corpus.py`
（守卫白名单已登记）；戏库原料复用 store.py

**Testing**: pytest 离线（内置小语料 fixture + mock 嵌入/LLM 接缝）；
全量入库为真机任务

**Target Platform**: Windows 本机

**Project Type**: cli/library + MCP server

**Performance Goals**: 全库入库 < 30 分钟；单词检索亚秒（FTS5）；
精排仅命中集（≤200 块）

**Constraints**: 藏书目录只读；入库零 LLM；嵌入/转写只在检索与落料时
按量发生

**Scale/Scope**: 14094 部、约 232 万块（500 字块）、库约 8-10GB

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 依据 |
|------|------|------|
| I. 契约先行 | PASS | contracts/corpus.md 先行（入库/检索/古籍腿/MCP 签名） |
| II. 单一胶水层 | PASS | 业务在 orchestrator/corpus.py（新）；db/corpus.py 只存储 |
| III. 存储单一入口 | PASS+修正 | 文库域单一入口 db/corpus.py；宪章 III 补"每存储域"
  措辞（PATCH 修订，本特性内完成） |
| IV. 适配器隔离与 Mock 基线 | PASS | 嵌入/LLM 均接缝注入，离线 mock 全覆盖 |
| V. UV 统一依赖 | PASS | 零新增包 |
| VI. 密钥与成本边界 | PASS | 入库零调用；嵌入 ≤200 块/次；转写按命中块计费 |
| VII. 一特性一分支 | PASS | 016-local-corpus |

无违规（III 为措辞修正非违规），无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/016-local-corpus/
├── plan.md / research.md / data-model.md / quickstart.md
├── contracts/corpus.md
└── tasks.md             # /skill:speckit-tasks 产出
```

### Source Code (repository root)

```text
db/
└── corpus.py            # spike 升级：schema v2（元数据/结构列）+ 批量入库 +
                         #   检索三件套 + 命中集嵌入精排

orchestrator/
├── corpus.py            # 新增：古籍腿业务（检索→转写→入原料表）+
                         #   DM 史料源装配
├── research.py          # 修改：research_material 接古籍腿（降级标注）
├── world.py             # 修改：DMOptions.use_corpus 开关 → dm_knowledge 扩展
└── mcp_server.py        # 修改：corpus_search / corpus_browse 工具

scripts/
└── corpus_ingest.py     # 新增：批量入库 CLI（walk 目录 + 报告 + 失败续跑）

tests/contract/
└── test_corpus.py       # 新增：入库/结构分块/检索/过滤/古籍腿/精排 mock

.specify/memory/constitution.md  # 修正：III 补"每存储域单一入口"（PATCH）
```

**Structure Decision**: 单项目布局；存储层 db/corpus.py、业务层
orchestrator/corpus.py 分层，与宪章 II/III 对齐。

## 设计要点（Phase 1 摘要）

1. **结构感知分块**（research.md R1）：标题行识别（`　　`起头的短行 +
   `卷[一二三四…]`模式）切大节 → 节内句读聚合约 500 字 → 块带
   chapter/section/heading_path。无标点文本退化定长 + 书目注记。
2. **幂等入库**（R2）：content_hash 不变 → 整书跳过；变 → 整书重入
   （块全删重建，FTS 同步）。失败书登记原因继续。
3. **古籍腿**（R3）：`research_material` 前插一步——corpus 检索 top-k →
   llm 转写（古文→现代汉语摘要）→ put_material(retriever=
   "corpus:<book_id>", context=原文+转写)；古籍库缺失/零命中静默降级
   并标注。
4. **DM 史料源**（R4）：DMOptions.use_corpus=True 时 build_dm_knowledge
   先以场景名+角色名检索 corpus 取料（预算内优先），再拼调研原料。
5. **精排**（R5）：命中 >1 且 use_rerank 时，命中集（≤200）细分至
   ≤300 字嵌向量，与 query 余弦重排；服务离线降级关键词序并标注。

## Constitution Check（Phase 1 复审）

契约先行（I）；存储/业务分层（II/III，含措辞修正任务）；mock 基线（IV）；
零新依赖（V）；成本闸门逐层可见（VI）；分支隔离（VII）。**全部 PASS。**
