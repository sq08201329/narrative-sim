# Feature Specification: 古籍文库（本地语料检索层）

**Feature Branch**: `016-local-corpus`

**Created**: 2026-10-25

**Status**: Draft

**Input**: User description: "中华古籍藏书（1.16 亿字，14094 部 txt）入库：批量入库 + 结构感知分块 + 关键词检索主力 + 按需嵌入精排 + 调研管线接腿 + MCP 工具。"

## 背景与动机

本机藏有中华古籍文库（`D:\课程\来自：分享\206-中华十部古籍藏书11.6亿汉字`，
十藏分类、txt 纯文本、文件名带书名-朝代-作者）。这是一手史料武库：
调研深度、DM 裁决史实依据、仿真世界细节、创作核查基准都由此升级。

spike 已验证（`db/corpus.py` 单书入库 + FTS5 trigram 检索，梦粱录 240 块，
皇城司/茶肆/夜市原文命中）。本特性把它转正为项目级能力。

**已实测的硬约束**：
- 嵌入服务吞吐约 480-600ms/块且上下文约 400 字 → **全量嵌入不可行**
  （约需 21 天连续运行），检索以关键词为主力、嵌入只对命中集按需精排
- 古籍多为 GB18030 编码，入库需探测转 UTF-8
- 块级溯源要到篇目（"卷十六·茶肆"），spike 的标点聚合切块做不到

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 全库入库与结构感知检索 (Priority: P1)

把藏书全量入库（十藏 14094 部），切块识别卷/篇目结构，关键词检索命中
结果直接报"书名·卷·篇目"级出处；支持按藏/朝代/作者过滤与书目浏览。

**Why this priority**: 这是一切的地基——库不成，检索腿、MCP、DM 注入
都无从谈起。

**Independent Test**: 入库后检索"皇城司"命中《梦粱录》且出处到篇目；
按"史藏+宋"过滤结果全集正确；全库块数与字数符合预期规模。

**Acceptance Scenarios**:

1. **Given** 藏书目录，**When** 批量入库，**Then** 14094 部全部登记书目
   （书名/朝代/作者/藏/类/哈希/块数），正文切块入库，编码统一 UTF-8，
   重复入库幂等（哈希不变则跳过）。
2. **Given** 已入库，**When** 检索"茶肆"，**Then** 命中块带来源
   "梦粱录·卷十六·茶肆"级 heading_path（spike 的卷目混排问题消除）。
3. **Given** 已入库，**When** 按 collection=史藏 过滤检索，**Then**
   结果只含史藏书目。
4. **Given** 入库中途失败（坏文件/编码异常），**When** 发生，**Then**
   该书标记失败原因并跳过，不阻断后续书，已有数据不损坏。

---

### User Story 2 - 调研管线接古籍腿 (Priority: P2)

立项调研/单资产调研时，古籍库作为与 web 并列的检索源：query 先命中
典籍原文，转写摘要后按既有口径入原料表（带来源书目标记），与 web
结果共存；防重复漏斗对古籍命中同样生效。

**Why this priority**: 这是古籍库进入生产线的主通道——史料从"网文
摘要"升级为"典籍原文"。

**Independent Test**: 对一个宋代题材 query 跑调研，原料表出现来源为
典籍的条目，retriever 标记可区分。

**Acceptance Scenarios**:

1. **Given** 古籍库就绪，**When** 调研"南宋皇城司"，**Then** 原料表新增
   条目：context 含典籍原文/转写，retriever 标记为古籍通道（含书名篇目）。
2. **Given** 古籍无命中，**When** 调研，**Then** 正常走 web 腿，不报错。
3. **Given** 古籍库离线/缺失，**When** 调研，**Then** 降级为纯 web 腿并
   在结果中标注古籍通道不可用。

---

### User Story 3 - 检索面开放（MCP + DM 注入源） (Priority: P2)

bot 与创作核查 agent 经 MCP 直接检索古籍（关键词 + 过滤 + 出处）；
DM 裁决的 dm_knowledge 可从古籍命中取料（010 注入机制的语料源扩展）。

**Why this priority**: 开放检索面让创作核查自立（出处自己查），DM 注入
让裁决吃典籍——都是既有机制的语料源扩展，同级 P2。

**Independent Test**: MCP 调 corpus_search 命中并返回篇目出处；
DMOptions 开古籍源后 dm_knowledge 含典籍内容。

**Acceptance Scenarios**:

1. **Given** 服务在线，**When** MCP 调 corpus_search("夜禁")，**Then**
   返回命中块（书名/篇目/原文片段），零外部调用。
2. **Given** 启用古籍源，**When** 组世界带 DM，**Then** dm_knowledge 预算内
   含相关典籍段落（与调研原料并存，预算内古籍优先或按比例——实现时
   写死其一并进契约）。

---

### User Story 4 - 命中集按需嵌入精排 (Priority: P3)

关键词命中集（几十~几百块）经嵌入服务重排，解决同义异形
（"密探" vs "察事"）；块长按嵌入模型上下文约束（约 300 字）二次细分。

**Why this priority**: 质量增强层；关键词已兜住准确性底线（古文专有名词
原字命中），嵌入补召回率。实测约束决定它只能按需。

**Independent Test**: 现代汉语 query（"密探"）经精排能浮出不含该词但
语义相关的古文块（"察事""逻卒"），且只对命中集计费。

**Acceptance Scenarios**:

1. **Given** 关键词命中 50 块，**When** 开精排，**Then** 返回序按语义
   相关度重排，嵌入调用次数 = 命中块数（不多嵌）。
2. **Given** 嵌入服务离线，**When** 检索，**Then** 降级为纯关键词序，
   结果标注精排不可用。

---

### Edge Cases

- 无标点抄本（无句读）：切块退化为定长截断，不报错，书目注记。
- 文件名不合"书名-朝代-作者"格式：朝代/作者留空入库，不拒绝。
- 部书内容为空或仅空白：登记书目、零块，标记 empty。
- 检索词全库无命中：返回空集合并附带书目规模（共 N 部 M 块）提示。
- 同一书名多版本（不同朝代作者）：按文件名全量区分，不合并。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 批量入库藏书目录全部 txt：编码探测
  （UTF-8/GB18030）、文件名元数据解析、内容哈希判重幂等、单书失败
  跳过不阻断、入库报告（成功/失败/空书计数）。
- **FR-002**: 切块 MUST 结构感知：先按卷/篇目标题切大节，节内按句读
  聚合（约 500 字），块带 chapter/section/heading_path 元数据；无标点
  文本退化定长截断并注记。
- **FR-003**: 检索 MUST 支持：关键词（FTS5 trigram，2 字回退 LIKE）、
  藏/类/朝代/作者过滤、书目浏览（按藏/类列书目）。
- **FR-004**: 检索结果 MUST 带篇目级出处（书名 + heading_path +
  原文片段 + 块号）。
- **FR-005**: 古籍库 MUST 为独立共享库（data/corpus.db），全部戏可用；
  存储单一入口为 db/corpus.py（宪章 III 按"每存储域单一入口"修正措辞，
  本特性含宪章 PATCH 修订）。
- **FR-006**: 调研管线 MUST 支持古籍腿：query → 古籍命中 → 转写摘要 →
  入原料表（retriever 标记含书名篇目）；与 web 腿并存、互不妨碍、
  古籍离线时降级并标注。
- **FR-007**: MCP MUST 新增 corpus_search / corpus_browse 工具（关键词 +
  过滤 + 出处；零外部调用）。
- **FR-008**: DM dm_knowledge MUST 可选从古籍命中取料（预算内与调研
  原料的组合策略实现时写死并进契约）。
- **FR-009**: 嵌入精排 MUST 只作用于关键词命中集，逐块计费可见，
  嵌入服务离线时降级为关键词序并标注；块长适配模型上下文（约 300 字）。
- **FR-010**: 离线测试零外部调用（嵌入精排 mock）；既有测试无回归。

### Key Entities

- **books（书目）**: book_id / title / dynasty / author / category_l1（藏）/
  category_l2（类）/ content_hash / chunk_count / char_count / path /
  ingested_at / 注记（empty / 无标点退化 / 失败原因）。
- **chunks（块）**: book_id / seq / chapter / section / heading_path / text。
- **chunks_fts**: trigram FTS 索引（既有 spike 结构）。
- **古籍原料**: research_materials 复用——retriever 标记
  `corpus:<book_id>`，context 为原文+转写。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 全库入库完成率 ≥ 99%（失败书有原因记录），重复入库
  零重复块（幂等可验）。
- **SC-002**: "皇城司""茶肆""夜市"等主题词检索 100% 命中《梦粱录》
  对应篇目，出处到卷/篇目级。
- **SC-003**: 古籍腿调研产出原料条目，retriever 溯源到书名篇目，
  人工核对内容与原文一致。
- **SC-004**: MCP corpus_search 亚秒级返回（单库全文）。
- **SC-005**: 离线测试全绿零外部调用；既有 242 项无回归。

## Assumptions

- 藏书目录只读，永不写回原目录。
- 嵌入精排的命中集上限默认 200 块（成本闸），可配。
- 古籍转写（古文→现代汉语）发生在原料落库时（调研管线 LLM），
  入库层不做内容智能。
- 全量嵌入/向量库不做（实测不可行）；将来换 GPU 嵌入服务再议。
- 诗藏等韵文的分块质量不在本期验收范围（按句读聚合即可）。
