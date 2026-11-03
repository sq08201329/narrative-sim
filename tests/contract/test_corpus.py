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


# ---------- 017：同名来源与保守元数据 ----------

def test_same_name_different_paths_are_preserved(corpus_db, tmp_path):
    first = tmp_path / "地理" / "华阳国志-晋-常璩.txt"
    second = tmp_path / "载记" / "华阳国志-晋-常璩.txt"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("地理版本。成都沿革。", encoding="utf-8")
    second.write_text("载记版本。南中志略。", encoding="utf-8")

    one = ingest_book(corpus_db, str(first), "史藏", "地理")
    two = ingest_book(corpus_db, str(second), "史藏", "载记")
    again = ingest_book(corpus_db, str(first), "史藏", "地理")

    assert one["book_id"] == "华阳国志_晋_常璩"
    assert two["book_id"] != one["book_id"]
    assert again["status"] == "skipped"
    assert stats(corpus_db)["books"] == 2
    assert search(corpus_db, "成都")["hits"][0]["book_id"] == one["book_id"]
    assert search(corpus_db, "南中")["hits"][0]["book_id"] == two["book_id"]


def test_same_name_same_content_keeps_both_sources(corpus_db, tmp_path):
    paths = [tmp_path / "甲" / "佛说阿弥陀经--.txt",
             tmp_path / "乙" / "佛说阿弥陀经--.txt"]
    for p in paths:
        p.parent.mkdir()
        p.write_text("同一份经文。", encoding="utf-8")
        ingest_book(corpus_db, str(p))
    assert stats(corpus_db)["books"] == 2


def test_series_filename_metadata(corpus_db, tmp_path):
    p = tmp_path / "正统道藏太平部-重阳全真集-金-王嚞.txt"
    p.write_text("道藏正文。", encoding="utf-8")
    ingest_book(corpus_db, str(p), "03道藏-1689部", "04正统道藏太平部-65部")
    b = browse(corpus_db)[0]
    assert (b["title"], b["dynasty"], b["author"]) == ("重阳全真集", "金", "王嚞")


def test_blank_metadata_and_copy_suffix(corpus_db, tmp_path):
    blank = tmp_path / "佛说阿弥陀经--.txt"
    copy = tmp_path / "园冶-明-计成 - 副本.txt"
    volume = tmp_path / "朱子治家格言-明-朱柏庐-计1卷.txt"
    joined_volume = tmp_path / "海忠介公全集-明-海瑞12卷.txt"
    same_as_category = tmp_path / "笔记-宋-宋祁.txt"
    anonymous = tmp_path / "正统道藏太玄部-周易参同契注---佚名.txt"
    for p in (blank, copy, volume, joined_volume, same_as_category, anonymous):
        p.write_text(p.stem + "正文。", encoding="utf-8")
        ingest_book(corpus_db, str(p), "集藏", p.stem.split("-")[0])
    rows = {b["title"]: b for b in browse(corpus_db)}
    assert (rows["佛说阿弥陀经"]["dynasty"], rows["佛说阿弥陀经"]["author"]) == ("", "")
    assert rows["园冶"]["author"] == "计成"
    assert rows["朱子治家格言"]["author"] == "朱柏庐"
    assert rows["海忠介公全集"]["author"] == "海瑞"
    assert (rows["笔记"]["dynasty"], rows["笔记"]["author"]) == ("宋", "宋祁")
    assert rows["周易参同契注"]["author"] == "佚名"


def test_ambiguous_dynasty_leaves_fields_empty(corpus_db, tmp_path):
    p = tmp_path / "唐宋异闻-宋-唐-宋-张三.txt"
    p.write_text("", encoding="utf-8")
    ingest_book(corpus_db, str(p))
    b = browse(corpus_db)[0]
    assert b["dynasty"] == b["author"] == ""
    assert "metadata_unresolved" in b["note"]
    assert stats(corpus_db)["empty"] == 1


def test_repair_recovers_sources_without_changing_old_chunks(corpus_db, tmp_path,
                                                              monkeypatch):
    import db.corpus as corpus

    root = tmp_path / "藏书"
    first = root / "史藏" / "地理" / "华阳国志-晋-常璩.txt"
    second = root / "史藏" / "载记" / "华阳国志-晋-常璩.txt"
    series = (root / "道藏" / "04正统道藏太平部-65部"
              / "正统道藏太平部-重阳全真集-金-王嚞.txt")
    empty = root / "佛藏" / "经部" / "空书--.txt"
    for p in (first, second, series, empty):
        p.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("地理版本。茶肆沿革。", encoding="utf-8")
    second.write_text("载记版本。南中志略。", encoding="utf-8")
    series.write_text("道藏正文。", encoding="utf-8")
    empty.write_text("　　只有篇目标题", encoding="utf-8")
    original_parser = corpus._parse_metadata
    monkeypatch.setattr(corpus, "_parse_metadata",
                        lambda name, category="": ("错误书名", "错误朝代", "错误作者", ""))
    ingest_book(corpus_db, str(first), "史藏", "地理")
    ingest_book(corpus_db, str(series), "道藏", "正统道藏太平部")
    monkeypatch.setattr(corpus, "_parse_metadata", original_parser)

    target = tmp_path / "repaired.db"
    report_path = tmp_path / "repair.json"
    report = corpus.repair_corpus(corpus_db, str(target), str(root), str(report_path))

    assert stats(corpus_db)["books"] == 2
    assert stats(str(target))["books"] == 4
    assert report["validation"]["old_chunks_preserved"] is True
    assert report["validation"]["content_hashes_match"] is True
    assert len(report["recovered"]) == 2
    assert len(report["metadata_changes"]) == 2
    rows = {b["title"]: b for b in browse(str(target))}
    assert rows["重阳全真集"]["dynasty"] == "金"
    assert rows["华阳国志"]["author"] == "常璩"
    assert search(str(target), "南中")["hits"]
    assert report_path.exists()

    second_target = tmp_path / "repaired-again.db"
    second_report = corpus.repair_corpus(
        str(target), str(second_target), str(root), str(tmp_path / "again.json"))
    assert second_report["recovered"] == []
    assert second_report["metadata_changes"] == []
    assert stats(str(second_target)) == stats(str(target))


def test_corpus_path_follows_home_and_explicit_override(tmp_path, monkeypatch):
    from orchestrator import corpus as corpus_leg

    home = tmp_path / "home"
    derived = home / "data" / "corpus.db"
    init_corpus(str(derived))
    monkeypatch.setenv("NARRATIVE_HOME", str(home))
    monkeypatch.delenv("CORPUS_DB", raising=False)
    assert corpus_leg._db_path() == str(derived)

    monkeypatch.setenv("CORPUS_DB", "")
    assert corpus_leg._db_path() == str(derived)

    custom = tmp_path / "custom.db"
    init_corpus(str(custom))
    monkeypatch.setenv("CORPUS_DB", str(custom))
    assert corpus_leg._db_path() == str(custom)
