# Contract: 古籍文库（db/corpus.py + orchestrator/corpus.py + MCP）

**Feature**: 016-local-corpus | **Date**: 2026-10-25

本契约先行于实现（宪章 I）。

## 1. 存储层（db/corpus.py，schema v2）

```python
def init_corpus(db_path: str) -> str: ...
def ingest_book(db_path: str, txt_path: str,
                category_l1: str = "", category_l2: str = "") -> dict:
    """单书入库。返回 {book_id, chunks, chars, status}
    status: ingested / skipped（哈希一致幂等跳过）/ empty /
            failed（note 记原因）。抛异常只限库级错误。"""
def search(db_path: str, query: str, limit: int = 5,
           category_l1: str | None = None, dynasty: str | None = None,
           author: str | None = None, rerank: bool = False,
           embed=None) -> dict:
    """返回 {hits: [{book_id, title, heading_path, seq, text, snip}],
             rerank_degraded: bool}
    ≥3 字 FTS5 trigram；2 字 LIKE；过滤参数叠加 AND。
    rerank=True 且 2≤命中≤200 时经 embed 接缝重排（上限 200，超出截断
    并标注）；embed 异常 → 关键词序 + rerank_degraded=True。"""
def browse(db_path: str, category_l1: str | None = None,
           category_l2: str | None = None) -> list[dict]:
    """书目浏览：[{book_id, title, dynasty, author, category_l1,
    category_l2, chunk_count, char_count, note}]"""
def stats(db_path: str) -> dict:
    """{books, chunks, chars, failed, empty}"""
```

## 2. 业务层（orchestrator/corpus.py）

```python
CORPUS_DB = os.environ.get("CORPUS_DB", "data/corpus.db")

def corpus_materials(query: str, store: Store, top_k: int = 3,
                     chat=None) -> list[int]:
    """古籍腿：检索 top_k → LLM 转写 → put_material（retriever=
    corpus:<书名>·<篇目>）。返回原料行 id 列表。
    库缺失 → CorpusUnavailable（调用方降级标注）；零命中返回 []。"""

def corpus_knowledge(query: str, budget: int) -> str:
    """DM 史料源：检索取块拼进预算（用于 build_dm_knowledge 扩展）。"""
```

## 3. 既有模块扩参

```python
# orchestrator/research.py
def research_material(query, store, *, link_asset_id=None,
                      call_tool=None, use_corpus=True) -> int: ...
    # use_corpus=True：先古籍腿后 web 腿；古籍不可用降级标注继续 web
    # 古籍条目与 web 条目各自独立入原料表

# orchestrator/world.py
@dataclass
class DMOptions:
    ...
    use_corpus: bool = False   # True：dm_knowledge 先 corpus 后原料
```

## 4. MCP 工具

```python
def corpus_search(query: str, limit: int = 5,
                  category_l1: str | None = None,
                  dynasty: str | None = None) -> dict:
    """古籍全文检索（本地零成本）。返回 {hits: [{title, heading_path,
    snip, ...}], total_books}；库未建 → CorpusUnavailable。"""

def corpus_browse(category_l1: str | None = None,
                  category_l2: str | None = None) -> dict:
    """书目浏览。返回 {books: [...], total}。"""
```

错误词汇：`CorpusUnavailable`。

## 5. 批量入库 CLI（scripts/corpus_ingest.py）

```text
uv run python scripts/corpus_ingest.py <藏书根目录> [--db data/corpus.db]
  → 遍历 *.txt，逐部 ingest_book（目录第一/二层 → category_l1/l2）
  → 终报 {total, ingested, skipped, empty, failed:[{path, reason}]}
```

## 6. 宪章修正（R6，PATCH）

`.specify/memory/constitution.md` 原则 III 措辞："存储单一入口 store.py"
→ "每个存储域单一入口：戏库 store.py；古籍文库 db/corpus.py"。
版本 1.0.0 → 1.0.1（PATCH：澄清，非语义变更）。

## 7. 测试契约

- `tests/contract/test_corpus.py`（内置迷你语料 fixture，两本伪古籍含
  卷/篇目结构）：结构分块（chapter/section/heading_path 正确）/
  幂等（重入 skipped 零重复块）/ 编码探测 / 检索命中与出处 /
  过滤与浏览 / 2 字 LIKE 回退 / 精排 mock（重排 + 降级标记）/
  古籍腿（mock chat 转写 + 原料表留痕 + 零命中降级）/
  DM use_corpus 注入。
- `test_mcp_server.py` 追加双工具 + CorpusUnavailable + EXPECTED_TOOLS。
- 全部离线零外部调用；既有 242 项无回归。
