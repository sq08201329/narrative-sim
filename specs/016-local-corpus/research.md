# Research: 古籍文库

**Date**: 2026-10-25 | **Feature**: 016-local-corpus

spike 已解决大部分未知（编码、FTS5 trigram、切块、检索实证）。以下为转正
决策。

## R1: 结构感知分块——标题行启发式 + 句读聚合

- **Decision**: 两级切块。一级：识别标题行（全角空格 `　　`起头的短行、
  或匹配 `卷[一二三四五六七八九十百〇零\d]+` 的行）切出节，记
  chapter（卷号）/section（篇目名）；二级：节内按句读标点聚合至约
  500 字。全文无标题行命中 → 退化为纯句读聚合；无标点 → 定长截断。
- **Rationale**: spike 实测《梦粱录》版式（"　　卷十六　　茶　　肆"），
  启发式对该藏书集（同一整理方）足够；通用 OCR 级版面分析超出范围。
  heading_path 到篇目即可满足溯源（SC-002）。
- **Alternatives considered**: LLM 识别结构（入库层零智能原则，否决）；
  纯定长（丢失篇目出处，否决）。

## R2: 幂等批量入库——内容哈希整书粒度

- **Decision**: `content_hash`（UTF-8 正文 sha256）。入库时同 book_id：
  哈希一致 → 跳过；不一致 → 删旧块整书重建（FTS 先删后插，同事务）。
  单书异常捕获登记 `note` 列继续。
- **Rationale**: 书是天然原子单位；块级幂等无意义（分块规则升级时本来
  就要整书重建）。失败不阻断是 14094 部批量的基本生存能力（spec
  US1/AC4）。
- **规模预算**: spike 单书 229KB 约 1s（含 FTS）；全量约 10-30 分钟，
  可接受；CLI 输出进度与终报（SC-001）。

## R3: 古籍腿——检索 + LLM 转写 + 复用原料表

- **Decision**: `orchestrator/corpus.py` 新增 `corpus_materials(query,
  store, top_k=3)`：db 检索 top-k 块 → llm.chat 转写（"以下为古籍原文，
  给出其现代汉语摘要并保留专有名词"）→ `store.put_material(query,
  retriever="corpus:<book_id>·<heading_path>", context=原文+转写)`。
  `research.research_material` 增加 `use_corpus=True` 参数：先古籍腿后
  web 腿；corpus 库不存在/零命中 → 标注 `corpus_unavailable` 或
  `corpus_no_hit`，不报错。
- **Rationale**: 原料表与漏斗（009）零改动——同 query 的古籍条目天然
  命中精确缓存，跨戏复用免费。转写在落料时发生（入库零智能原则）。
- **证据**: research.py:234 research_material 的 call_tool 接缝与
  put_material 路径已支持任意 retriever 标签。

## R4: DM 史料源——corpus 优先，预算内再拼原料

- **Decision**: `DMOptions.use_corpus: bool = False`；为真时
  build_dm_knowledge 先以"场景名 + 角色名"检索 corpus（各 top-2），
  命中块原文入预算；剩余预算再填调研原料（既有逻辑）。
- **Rationale**: spec FR-008 要求策略写死——"古籍优先"的理由：典籍是
  一手史料，调研原料已是二手摘要。use_corpus 默认关（向后兼容锚点）。

## R5: 嵌入精排——命中集重排，服务降级兜底

- **Decision**: db/corpus.py `search(..., rerank=False)`；rerank=True 且
  命中 2-200 块时：块细分至 ≤300 字 → 003 服务嵌向量 → 与 query 余弦
  重排。嵌入经接缝注入（测试 mock）；服务异常 → 关键词序 +
  `rerank_degraded` 标记。
- **Rationale**: 实测约束（480-600ms/块、~400 字上限）决定只能按需；
  200 块上限约 1.6 分钟，可接受。命中 ≤1 块重排无意义。
- **Alternatives considered**: 全量预嵌（实测 21 天，否决）；换嵌入服务
  （超出本特性范围）。

## R6: 宪章 III 措辞修正（PATCH 1.0.1）

- **Decision**: "存储单一入口 store.py" → "每个存储域单一入口：戏库
  store.py；古籍文库 db/corpus.py"。PATCH 级（澄清非语义变更）。
- **Rationale**: spike 时守卫白名单已登记 corpus.py；措辞与实际架构
  对齐，避免后续每个新存储域都撞守卫。
