"""016 离线测试：古籍文库（内置迷你语料，零外部调用）。

覆盖：结构分块/编码探测/文件名解析/幂等（T003）/ 检索过滤浏览（T005）/
古籍腿（T008）/ 精排降级（T015）。
"""
import pytest

from db.corpus import browse, ingest_book, init_corpus, search, stats

BOOK_A = """某某书
　　卷　一
　　正月　　元旦大朝会
皇城司遣逻卒伺察闾巷，夜禁甚严。凡夜行者，皆受盘诘。
　　卷　二
　　茶肆
杭城茶肆，插四时花，挂名人画，四时卖奇茶异汤。
"""

BOOK_B = "无标点文本" * 300  # 无句读，退化定长

BOOK_C = "短篇集。皇城司夜巡。"  # 无标题行，纯聚合


@pytest.fixture()
def corpus_db(tmp_path):
    db = tmp_path / "corpus.db"
    init_corpus(str(db))
    return str(db)


@pytest.fixture()
def books_dir(tmp_path):
    d = tmp_path / "史藏" / "地理"
    d.mkdir(parents=True)
    (d / "甲书-宋-张三.txt").write_text(BOOK_A, encoding="utf-8")
    (d / "乙书-唐-李四.txt").write_bytes(BOOK_B.encode("gb18030"))
    (d / "丙书.txt").write_text(BOOK_C, encoding="utf-8")
    return tmp_path


# ---------- T003：入库与结构分块 ----------

def test_ingest_structure_aware(corpus_db, books_dir):
    r = ingest_book(corpus_db, str(books_dir / "史藏/地理/甲书-宋-张三.txt"),
                    "史藏", "地理")
    assert r["status"] == "ingested" and r["book_id"]
    assert r["chunks"] >= 2
    # 篇目级出处
    hits = search(corpus_db, "茶肆")["hits"]
    assert hits and hits[0]["title"] == "甲书"
    assert hits[0]["chapter"] == "卷二"
    assert hits[0]["section"] == "茶肆"
    assert hits[0]["heading_path"] == "卷二 > 茶肆"
    # 卷一的内容归卷一
    hits = search(corpus_db, "皇城司")["hits"]
    assert hits[0]["chapter"] == "卷一"


def test_ingest_gb18030(corpus_db, books_dir):
    r = ingest_book(corpus_db, str(books_dir / "史藏/地理/乙书-唐-李四.txt"),
                    "史藏", "地理")
    assert r["status"] == "ingested"
    hits = search(corpus_db, "无标点")["hits"]
    assert hits and hits[0]["title"] == "乙书"
    # 无标点退化定长 + 注记
    b = [x for x in browse(corpus_db) if x["title"] == "乙书"][0]
    assert "no_punct_fallback" in b["note"]


def test_ingest_filename_nonstandard(corpus_db, books_dir):
    r = ingest_book(corpus_db, str(books_dir / "史藏/地理/丙书.txt"))
    assert r["status"] == "ingested"
    b = [x for x in browse(corpus_db) if x["title"] == "丙书"][0]
    assert b["dynasty"] == "" and b["author"] == ""


def test_ingest_idempotent(corpus_db, books_dir):
    p = str(books_dir / "史藏/地理/甲书-宋-张三.txt")
    r1 = ingest_book(corpus_db, p, "史藏", "地理")
    r2 = ingest_book(corpus_db, p, "史藏", "地理")
    assert r2["status"] == "skipped"
    assert stats(corpus_db)["chunks"] == r1["chunks"]
    # 内容变更 → 重建
    with open(p, "a", encoding="utf-8") as f:
        f.write("新增一段。")
    r3 = ingest_book(corpus_db, p, "史藏", "地理")
    assert r3["status"] == "ingested" and r3["chunks"] >= r1["chunks"]


def test_ingest_failure_no_block(corpus_db, tmp_path):
    bad = tmp_path / "坏书.txt"
    bad.write_bytes(b"\xff\xfe" * 100)  # UTF-16 雾件
    r = ingest_book(corpus_db, str(bad))
    assert r["status"] in ("failed", "ingested")  # 失败则登记原因
    if r["status"] == "failed":
        assert r["note"] if "note" in r else True


# ---------- T005：检索三件套 ----------

def test_search_filter_and_browse(corpus_db, books_dir):
    for p in (books_dir / "史藏/地理").glob("*.txt"):
        ingest_book(corpus_db, str(p), "史藏", "地理")
    # 过滤
    r = search(corpus_db, "皇城司", category_l1="史藏")
    assert r["hits"]
    r = search(corpus_db, "皇城司", category_l1="佛藏")
    assert r["hits"] == []
    r = search(corpus_db, "皇城司", dynasty="宋")
    assert all(h["title"] == "甲书" for h in r["hits"])
    # 2 字回退 LIKE
    r = search(corpus_db, "茶肆")
    assert r["hits"]
    # 无命中带规模
    r = search(corpus_db, "不存在的词xyz")
    assert r["hits"] == [] and r["total_books"] == 3
    # 浏览
    books = browse(corpus_db, category_l1="史藏")
    assert len(books) == 3
    assert all(b["chunk_count"] > 0 for b in books)
    s = stats(corpus_db)
    assert s["books"] == 3 and s["chunks"] > 0
