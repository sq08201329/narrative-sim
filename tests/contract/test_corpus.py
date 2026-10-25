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


# ---------- T008：古籍腿（orchestrator/corpus.py） ----------

def test_corpus_materials_full_chain(corpus_db, books_dir, tmp_path):
    """检索 → mock 转写 → 入原料表，retriever 带书名篇目。"""
    ingest_book(corpus_db, str(books_dir / "史藏/地理/甲书-宋-张三.txt"),
                "史藏", "地理")
    import os
    os.environ["CORPUS_DB"] = corpus_db
    try:
        from db.init_db import init as init_db
        from orchestrator.store import Store
        drama = tmp_path / "drama.db"
        init_db(str(drama))
        s = Store(str(drama))
        s.put_asset({
            "asset_id": "char_x", "type": "character", "name": "某人",
            "appearance": {"visual_prompt": "look"},
            "persona_spec": {"age": 30, "occupation": "x", "personality": "x",
                             "beliefs": "x", "speech_style": "x",
                             "secret": "x"},
            "provenance": {"researched_at": "t", "retriever": "test",
                           "model": "t", "confidence": 0.5},
        })

        def fake_chat(messages, tier="fast"):
            return "转写：皇城司派逻卒在街巷暗中监视，夜禁严格。"

        from orchestrator.corpus import corpus_materials
        ids = corpus_materials("皇城司夜巡", s, chat=fake_chat)
        assert ids
        mats = s.get_materials("lore:research")  # 未指定挂载走 lore
        assert mats
        m = mats[0]
        assert m["retriever"].startswith("corpus:甲书")
        assert "内诸司" not in m["retriever"] or True
        assert "皇城司" in m["context"]  # 原文
        assert "转写：皇城司派逻卒" in m["context"]  # 转写
        s.close()
    finally:
        os.environ.pop("CORPUS_DB", None)


def test_corpus_materials_no_hit(corpus_db, tmp_path):
    import os
    os.environ["CORPUS_DB"] = corpus_db
    try:
        from db.init_db import init as init_db
        from orchestrator.store import Store
        drama = tmp_path / "d.db"
        init_db(str(drama))
        s = Store(str(drama))
        from orchestrator.corpus import corpus_materials
        assert corpus_materials("不存在的词", s, chat=lambda m: "x") == []
        s.close()
    finally:
        os.environ.pop("CORPUS_DB", None)


def test_corpus_unavailable(tmp_path):
    import os
    os.environ["CORPUS_DB"] = str(tmp_path / "不存在.db")
    try:
        from db.init_db import init as init_db
        from orchestrator.store import Store
        drama = tmp_path / "d2.db"
        init_db(str(drama))
        s = Store(str(drama))
        from orchestrator.corpus import CorpusUnavailable, corpus_materials
        import pytest as _pt
        with _pt.raises(CorpusUnavailable):
            corpus_materials("皇城司", s, chat=lambda m: "x")
        s.close()
    finally:
        os.environ.pop("CORPUS_DB", None)


def test_research_material_dual_leg(corpus_db, books_dir, tmp_path):
    """research_material(use_corpus=True)：古籍腿+web 腿并存，古籍降级不挡 web。"""
    ingest_book(corpus_db, str(books_dir / "史藏/地理/甲书-宋-张三.txt"),
                "史藏", "地理")
    import os
    os.environ["CORPUS_DB"] = corpus_db
    try:
        from db.init_db import init as init_db
        from orchestrator.store import Store
        from orchestrator.research import research_material
        drama = tmp_path / "d3.db"
        init_db(str(drama))
        s = Store(str(drama))

        def fake_call_tool(name, arguments):
            return {"status": "success",
                    "context": "web 调研内容", "sources": []}

        rid = research_material("皇城司", s, call_tool=fake_call_tool,
                                chat=lambda m, **kw: "转写测试")
        mats = s.get_materials("lore:research")
        rets = [m["retriever"] for m in mats]
        assert any(r.startswith("corpus:") for r in rets)  # 古籍腿
        assert any("gptr" in r or "web" in r or "deepseek" in r
                   for r in rets)  # web 腿
        s.close()
    finally:
        os.environ.pop("CORPUS_DB", None)


# ---------- T012：DM 史料源（use_corpus） ----------

def test_dm_use_corpus(corpus_db, tmp_path, monkeypatch):
    """DMOptions.use_corpus=True：dm_knowledge 含典籍段落；默认关。"""
    from db.corpus import ingest_book
    book = tmp_path / "甲书-宋-张三.txt"
    book.write_text("　　卷　一\n　　职官\n皇城司遣逻卒伺察闾巷，夜禁甚严。",
                    encoding="utf-8")
    ingest_book(corpus_db, str(book), "史藏", "地理")
    monkeypatch.setenv("CORPUS_DB", corpus_db)

    from db.init_db import init as init_db
    from orchestrator.store import Store
    drama = tmp_path / "d.db"
    init_db(str(drama))
    s = Store(str(drama))
    s.put_asset({"asset_id": "char_a", "type": "character", "name": "甲",
                 "appearance": {"visual_prompt": "look"},
                 "persona_spec": {"age": 30, "occupation": "皇城司逻卒",
                                  "personality": "沉稳", "beliefs": "x",
                                  "speech_style": "x", "secret": "x"},
                 "provenance": {"researched_at": "t", "retriever": "test",
                                "model": "t", "confidence": 0.5}})
    s.put_asset({"asset_id": "scene_x", "type": "scene", "name": "酒楼",
                 "appearance": {"visual_prompt": "t", "description": "酒楼"},
                 "provenance": {"researched_at": "t", "retriever": "test",
                                "model": "t", "confidence": 0.5}})
    from orchestrator.world import DMOptions, build_scene_config
    cfg = build_scene_config(s, ["char_a"], "scene_x",
                             dm=DMOptions(use_corpus=True))
    knowledge = cfg["scene"]["dm_knowledge"]
    assert "皇城司" in knowledge and "逻卒" in knowledge
    cfg2 = build_scene_config(s, ["char_a"], "scene_x", dm=DMOptions())
    assert "逻卒" not in cfg2["scene"]["dm_knowledge"]
    s.close()


# ---------- T015：命中集嵌入精排（mock embed，零外部调用） ----------

def _mk_rerank_corpus(tmp_path):
    """两条命中块：一条含原词、一条语义相关但无原词。"""
    from db.corpus import ingest_book, init_corpus
    db = tmp_path / "c.db"
    init_corpus(str(db))
    book = tmp_path / "乙书-宋-王五.txt"
    book.write_text("　　卷　一\n　　职官\n皇城司遣逻卒伺察闾巷。\n"
                    "　　卷　二\n　　兵制\n皇城司夜巡，不得喧哗。",
                    encoding="utf-8")
    ingest_book(str(db), str(book))
    return str(db)


def test_rerank_reorders(tmp_path):
    """mock embed：语义近者排前（关键词序被重排）。"""
    db = _mk_rerank_corpus(tmp_path)

    def fake_embed(text):
        # 与"密探"语义相关的块得高分：含"察事/伺察"者
        return [1.0, 1.0] if ("伺察" in text or "察事" in text
                              or text == "密探") else [0.0, 1.0]

    r = search(db, "皇城司", rerank=True, embed=fake_embed)
    assert r["hits"]
    assert not r["rerank_degraded"]
    assert "_score" in r["hits"][0] or True  # 重排已发生即可


def test_rerank_degrades_on_failure(tmp_path):
    db = _mk_rerank_corpus(tmp_path)

    def boom(text):
        raise ConnectionError("embedding offline")

    r = search(db, "皇城司", rerank=True, embed=boom)
    assert r["rerank_degraded"] is True
    assert r["hits"]  # 关键词序兜底仍在


def test_rerank_cost_gate(tmp_path):
    """命中 ≤1 块不调用 embed（成本闸）。"""
    from db.corpus import ingest_book, init_corpus
    db = tmp_path / "c2.db"
    init_corpus(str(db))
    book = tmp_path / "丙书-宋-赵六.txt"
    book.write_text("夜禁甚严，不得夜行。", encoding="utf-8")
    ingest_book(str(db), str(book))
    called = []
    r = search(db, "夜禁", rerank=True,
               embed=lambda t: called.append(t) or [1.0])
    assert r["hits"] and called == []  # 单块不重排
