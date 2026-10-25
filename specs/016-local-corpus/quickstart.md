# Quickstart: 古籍文库验证

**Feature**: 016-local-corpus | **Date**: 2026-10-25

## 离线验证（默认测试集，零外部调用）

```bash
uv run pytest -m "not real" -q
```

重点断言（tests/contract/test_corpus.py，内置迷你语料）：

1. 结构分块：含"卷/篇目"标题行的伪古籍切出 chapter/section/
   heading_path；无标点文本退化定长且书目注记 no_punct_fallback。
2. 幂等：重复入库同书 skipped，块数不变；改内容重入后块数刷新。
3. 检索：关键词命中带篇目级出处；collection/dynasty 过滤正确；
   2 字词走 LIKE；无命中返回空 + 书目规模。
4. 精排：mock embed 下重排生效；embed 抛错降级关键词序 +
   rerank_degraded=True。
5. 古籍腿：mock chat 转写入原料表，retriever 含书名篇目；零命中
   时 research_material 仅 web 腿且标注。
6. DM：DMOptions(use_corpus=True) 时 dm_knowledge 含典籍段落。

## 真机验收

```bash
# 1. 全量入库（约 10-30 分钟，后台）
uv run python scripts/corpus_ingest.py "/d/课程/来自：分享/206-中华十部古籍藏书11.6亿汉字"

# 2. 检索验收（SC-002）
uv run python -c "from db.corpus import search; import json
for h in search('data/corpus.db', '皇城司')['hits']: print(h['title'], h['heading_path'])"
# 预期：梦粱录·内诸司 等篇目级出处

# 3. 古籍腿调研（SC-003，花 LLM 转写费）
uv run python -c "
from orchestrator.store import Store
from orchestrator.research import research_material
s = Store('data/library.db')
print(research_material('南宋临安夜市', s))"

# 4. MCP 双工具（SC-004 亚秒）
# start_stack 起服务后 corpus_search("夜禁") / corpus_browse(category_l1="史藏")
```

## 边界

- 藏书目录只读，永不写回。
- 全量嵌入不做（实测约束见 spec 背景）。
