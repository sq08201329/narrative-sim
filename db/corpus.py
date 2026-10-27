"""古籍文库（016）：文库存储域单一入口（宪章 III v1.0.1）。

- 编码探测：UTF-8 → GB18030（藏书集实测多为 GB18030），统一 UTF-8 入库
- 结构感知分块（R1）：标题行（全角空格起头短行 / 卷[一二三…]）切节，
  节内句读聚合约 500 字；无标点退化定长截断 + note 注记
- 幂等：content_hash 整书粒度——一致 skipped，变更整书重建（事务内）
- 检索：FTS5 trigram（≥3 字）/ LIKE（2 字）+ 藏/朝代/作者过滤 +
  书目浏览；rerank 为命中集嵌入精排（接缝注入，R5）
"""
import hashlib
import re
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS books (
    book_id      TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    dynasty      TEXT NOT NULL DEFAULT '',
    author       TEXT NOT NULL DEFAULT '',
    category_l1  TEXT NOT NULL DEFAULT '',
    category_l2  TEXT NOT NULL DEFAULT '',
    path         TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    chunk_count  INTEGER NOT NULL,
    char_count   INTEGER NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    ingested_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id      TEXT NOT NULL REFERENCES books(book_id),
    seq          INTEGER NOT NULL,
    chapter      TEXT NOT NULL DEFAULT '',
    section      TEXT NOT NULL DEFAULT '',
    heading_path TEXT NOT NULL DEFAULT '',
    text         TEXT NOT NULL,
    bi           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_chunks_book ON chunks(book_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id', tokenize='trigram'
);
-- 二元索引（unicode61，external-content 挂 chunks.bi）：
-- CJK 两字词 trigram 不支持，bi 列存"夜市 市物 物件"式二元流，
-- 索引由 'rebuild' 整建（C 层批量，远快于逐行 INSERT）
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_bi USING fts5(
    bi, content='chunks', content_rowid='id', tokenize='unicode61'
);
"""

_CHAPTER_RE = re.compile(r"卷[\s　]*[一二三四五六七八九十百〇零\d]+")
_HEADING_RE = re.compile(r"^[　\s]*(\S.{0,18}?)\s*$")
_SENT_SPLIT = re.compile(r"(?<=[。！？；])")


def _bigrams(text: str) -> str:
    """文本 → 空格分隔二元流（unicode61 按空格切 token = 二元组）。"""
    t = re.sub(r"\s+", "", text)
    return " ".join(t[i:i + 2] for i in range(len(t) - 1))


def init_corpus(db_path: str) -> str:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(DDL)
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(chunks)").fetchall()}
        if "bi" not in cols:
            conn.execute(
                "ALTER TABLE chunks ADD COLUMN bi TEXT NOT NULL DEFAULT ''")
        conn.commit()
    finally:
        conn.close()
    return db_path


def _read_text(path: Path) -> tuple[str, str]:
    """读入并归一 UTF-8。返回 (文本, 编码注记)。

    BOM 优先（UTF-16 藏书实测存在）；UTF-8 → GB18030 严格；
    个别坏字节（宋史等 8 部实测）→ GB18030 替换字符有损兜底 +
    encoding_lossy 注记。
    """
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), ""
        except UnicodeDecodeError:
            # BOM 在但中途有非法代理项（随息居饮食谱实测）→ 有损兜底
            return raw.decode("utf-16", errors="replace"), "encoding_lossy"
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc), ""
        except UnicodeDecodeError:
            continue
    return raw.decode("gb18030", errors="replace"), "encoding_lossy"


_DYNASTIES = frozenset({
    "夏", "商", "周", "西周", "东周", "春秋", "战国", "秦", "汉", "西汉",
    "东汉", "三国", "魏", "蜀汉", "吴", "晋", "西晋", "东晋", "南北朝",
    "南朝", "北朝", "宋", "南朝宋", "齐", "梁", "陈", "北魏", "东魏",
    "西魏", "北齐", "北周", "隋", "唐", "五代", "五代十国", "后梁",
    "后唐", "后晋", "后汉", "后周", "十国", "前蜀", "后蜀", "南唐",
    "南汉", "北汉", "北宋", "南宋", "辽", "金", "西夏", "元", "明",
    "清", "民国", "中华民国",
})
_VOLUME_RE = re.compile(r"^(?:计|共|·)?[\d一二三四五六七八九十百〇零]+卷$")


def _category_label(value: str) -> str:
    return re.sub(r"-\d+部$", "", re.sub(r"^\d+", "", value)).strip()


def _parse_metadata(name: str, category_l2: str = "") -> tuple[str, str, str, str]:
    stem = Path(name).stem
    parts = [part.strip() for part in stem.split("-")]
    parts = [part for part in parts if part and part != "副本"]
    while parts and _VOLUME_RE.fullmatch(parts[-1]):
        parts.pop()
    if not parts:
        return stem, "", "", "metadata_unresolved"

    label = _category_label(category_l2)
    series_suffix = parts[0][len(label):] if label else ""
    series_match = bool(label) and (
        parts[0] == label or (series_suffix.endswith("类")
                              and len(series_suffix) <= 4))
    if len(parts) > 1 and series_match and parts[1] not in _DYNASTIES:
        parts = parts[1:]
    dynasty_indexes = [i for i, part in enumerate(parts) if part in _DYNASTIES]
    unresolved = ""
    if len(dynasty_indexes) > 1:
        return "-".join(parts), "", "", "metadata_unresolved"

    if not dynasty_indexes:
        if len(parts) > 1 and parts[-1] == "佚名":
            return "-".join(parts[:-1]), "", "佚名", ""
        return "-".join(parts) or stem, "", "", unresolved
    i = dynasty_indexes[0]
    dynasty = parts[i]
    author = parts[i + 1] if i + 1 < len(parts) else ""
    author = re.sub(r"\d+(?:卷|回)?$", "", author).strip()
    if i + 1 < len(parts) and not author:
        unresolved = "metadata_unresolved"
        dynasty = ""
    title_parts = parts[:i]
    if author and i + 2 < len(parts):
        title_parts += parts[i + 2:]
    title = "-".join(title_parts).strip()
    if not title:
        return stem, "", "", "metadata_unresolved"
    return title, dynasty, author, unresolved


def _parse_filename(name: str) -> tuple[str, str, str]:
    title, dynasty, author, _ = _parse_metadata(name)
    return title, dynasty, author


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 20:
        return False
    if _CHAPTER_RE.search(s):
        return True
    # 全角空格起头的短行视为篇目标题（藏书集版式，R1）
    return line.startswith("　") and "。" not in s


def _split_sections(text: str) -> list[tuple[str, str, str]]:
    """→ [(chapter, section, body)]。chapter/section 可为 ''。"""
    sections: list[tuple[str, str, str]] = []
    chapter = ""
    section = ""
    buf: list[str] = []
    for line in text.splitlines():
        if _is_heading(line):
            if buf:
                sections.append((chapter, section, "\n".join(buf)))
                buf = []
            s = line.strip()
            m = _CHAPTER_RE.search(s)
            if m:
                chapter = m.group(0).replace("　", "").replace(" ", "")
                rest = s[m.end():].strip()
                section = rest
            elif s:
                section = s
            continue
        buf.append(line)
    if buf:
        sections.append((chapter, section, "\n".join(buf)))
    return sections


def _aggregate(body: str, size: int) -> list[str]:
    if not re.search(r"[。！？；]", body):
        return None  # 无标点信号，调用方退化定长
    out, buf = [], ""
    for s in _SENT_SPLIT.split(body):
        if len(buf) + len(s) > size and buf:
            out.append(buf)
            buf = ""
        buf += s
    if buf.strip():
        out.append(buf)
    return [c.strip() for c in out if c.strip()]


def _chunk(text: str, size: int = 500) -> tuple[list[tuple[str, str, str]], bool]:
    """→ ([(heading_path, chapter, text)], no_punct)。"""
    out: list[tuple[str, str, str]] = []
    no_punct = False
    for chapter, section, body in _split_sections(text):
        hp = " > ".join(x for x in (chapter, section) if x)
        blocks = _aggregate(body, size)
        if blocks is None:
            no_punct = True
            blocks = [body[i:i + size] for i in range(0, len(body), size)]
        for b in blocks:
            if b.strip():
                out.append((hp, chapter, section, b.strip()))
    return out, no_punct


def _book_id(conn: sqlite3.Connection, path: Path) -> str:
    base = re.sub(r"\W+", "_", path.stem)
    row = conn.execute("SELECT path FROM books WHERE book_id=?", (base,)).fetchone()
    if row is None or Path(row[0]).resolve() == path.resolve():
        return base
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
    candidate = f"{base}_{digest}"
    row = conn.execute(
        "SELECT path FROM books WHERE book_id=?", (candidate,)).fetchone()
    if row is not None and Path(row[0]).resolve() != path.resolve():
        raise ValueError(f"book_id 路径哈希冲突: {path}")
    return candidate


def ingest_book(db_path: str, txt_path: str,
                category_l1: str = "", category_l2: str = "") -> dict:
    """单书入库（契约 §1）：幂等/失败登记/事务内 FTS 同步。"""
    p = Path(txt_path)
    title, dynasty, author, metadata_note = _parse_metadata(p.name, category_l2)
    base = {"book_id": re.sub(r"\W+", "_", p.stem),
            "chunks": 0, "chars": 0, "note": ""}
    try:
        text, enc_note = _read_text(p)
    except (OSError, ValueError) as e:
        return {**base, "status": "failed", "note": str(e)}

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    conn = sqlite3.connect(db_path)
    try:
        book_id = _book_id(conn, p)
        base["book_id"] = book_id
        row = conn.execute(
            "SELECT content_hash FROM books WHERE book_id=?", (book_id,)
        ).fetchone()
        if row and row[0] == digest:
            return {**base, "status": "skipped"}

        blocks, no_punct = _chunk(text)
        note = " ".join(x for x in (
            enc_note, "no_punct_fallback" if no_punct else "", metadata_note,
            "empty" if not blocks else "") if x)
        with conn:  # 单书一事务：要么全进要么全滚回
            old = [r[0] for r in conn.execute(
                "SELECT id FROM chunks WHERE book_id=?", (book_id,)).fetchall()]
            if old:
                marks = ",".join("?" * len(old))
                conn.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({marks})",
                             old)
                for rid in old:
                    conn.execute(
                        "INSERT INTO chunks_bi(chunks_bi, rowid, bi)"
                        " VALUES('delete', ?, (SELECT bi FROM chunks"
                        " WHERE id=?))", (rid, rid))
                conn.execute("DELETE FROM chunks WHERE book_id=?", (book_id,))
            conn.execute("DELETE FROM books WHERE book_id=?", (book_id,))
            conn.execute(
                "INSERT INTO books(book_id, title, dynasty, author,"
                " category_l1, category_l2, path, content_hash, chunk_count,"
                " char_count, note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (book_id, title, dynasty, author, category_l1, category_l2,
                 str(p), digest, len(blocks), len(text), note))
            for i, (hp, chapter, section, body) in enumerate(blocks):
                cur = conn.execute(
                    "INSERT INTO chunks(book_id, seq, chapter, section,"
                    " heading_path, text, bi) VALUES(?,?,?,?,?,?,?)",
                    (book_id, i, chapter, section, hp, body,
                     _bigrams(body)))
                conn.execute(
                    "INSERT INTO chunks_fts(rowid, text) VALUES(?,?)",
                    (cur.lastrowid, body))
                conn.execute(
                    "INSERT INTO chunks_bi(rowid, bi) VALUES(?,?)",
                    (cur.lastrowid, _bigrams(body)))
        return {**base, "status": "ingested" if blocks else "empty",
                "chunks": len(blocks), "chars": len(text), "note": note}
    finally:
        conn.close()


def search(db_path: str, query: str, limit: int = 5,
           category_l1: str | None = None, dynasty: str | None = None,
           author: str | None = None, rerank: bool = False,
           embed=None) -> dict:
    """检索（契约 §1）：关键词主力 + 过滤 + 可选命中集精排。

    CJK 无分词：query 按空白拆词；≥3 字词切滑动三元组走 FTS5（OR+rank），
    短词（<3 字）走 LIKE 补召回，两路结果合并去重（FTS 命中优先）。
    无三元组时纯 LIKE。限定词不一票否决（OR 语义）。
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        where, args = [], []
        if category_l1:
            where.append("b.category_l1 = ?")
            args.append(category_l1)
        if dynasty:
            where.append("b.dynasty = ?")
            args.append(dynasty)
        if author:
            where.append("b.author = ?")
            args.append(author)
        filt = ("AND " + " AND ".join(where)) if where else ""

        tris, shorts = [], []
        for tok in query.split():
            if len(tok) >= 3:
                tris += [tok[i:i + 3] for i in range(len(tok) - 2)]
            elif tok:
                shorts.append(tok)

        cols = ("c.id AS cid, c.book_id, b.title, c.seq, c.chapter,"
                " c.section, c.heading_path, c.text")
        cap = 200 if rerank else limit
        hits: list[dict] = []
        seen: set[int] = set()

        if tris:
            fts_q = " OR ".join(f'"{t}"' for t in tris)
            sql = (
                f"SELECT {cols},"
                " snippet(chunks_fts, 0, '【', '】', '…', 32) AS snip"
                " FROM chunks_fts f JOIN chunks c ON c.id = f.rowid"
                " JOIN books b ON b.book_id = c.book_id"
                f" WHERE chunks_fts MATCH ? {filt} ORDER BY rank LIMIT ?"
            )
            for r in conn.execute(sql, [fts_q, *args, cap]).fetchall():
                d = dict(r)
                if d["cid"] not in seen:
                    seen.add(d["cid"])
                    hits.append(d)

        # 短词分流：2 字走二元索引（chunks_bi），1 字留 LIKE
        bis = [t for t in shorts if len(t) == 2]
        ones = [t for t in shorts if len(t) == 1]
        if bis:
            bi_q = " OR ".join(f'"{t}"' for t in bis)
            sql = (
                f"SELECT {cols}, c.text AS snip"
                " FROM chunks_bi bi JOIN chunks c ON c.id = bi.rowid"
                " JOIN books b ON b.book_id = c.book_id"
                f" WHERE chunks_bi MATCH ? {filt} ORDER BY rank LIMIT ?"
            )
            for r in conn.execute(sql, [bi_q, *args, cap]).fetchall():
                d = dict(r)
                if d["cid"] not in seen:
                    seen.add(d["cid"])
                    hits.append(d)

        terms = (ones or ([query.strip()] if not (tris or bis) else []))
        if terms:
            likes = " OR ".join("c.text LIKE ?" for _ in terms)
            sql = (
                f"SELECT {cols}, c.text AS snip"
                " FROM chunks c JOIN books b ON b.book_id = c.book_id"
                f" WHERE ({likes}) {filt} LIMIT ?"
            )
            for r in conn.execute(sql, [*[f"%{t}%" for t in terms],
                                      *args, cap]).fetchall():
                d = dict(r)
                if d["cid"] not in seen:
                    seen.add(d["cid"])
                    hits.append(d)

        degraded = False
        if rerank and len(hits) >= 2 and embed is not None:
            try:
                hits = _rerank(query, hits, embed)
            except Exception:
                degraded = True
        return {"hits": hits[:limit], "total_books": total_books,
                "rerank_degraded": degraded}
    finally:
        conn.close()


def _rerank(query: str, hits: list[dict], embed) -> list[dict]:
    """命中集嵌入精排：块细分 ≤300 字取最强分（R5，模型上下文约束）。"""
    qv = embed(query)
    for h in hits:
        parts = [h["text"][i:i + 300] for i in range(0, len(h["text"]), 300)]
        h["_score"] = max(_cos(qv, embed(p)) for p in parts)
    return sorted(hits, key=lambda h: -h["_score"])


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def browse(db_path: str, category_l1: str | None = None,
           category_l2: str | None = None) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where, args = [], []
        if category_l1:
            where.append("category_l1 = ?")
            args.append(category_l1)
        if category_l2:
            where.append("category_l2 = ?")
            args.append(category_l2)
        filt = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            "SELECT book_id, title, dynasty, author, category_l1,"
            f" category_l2, chunk_count, char_count, note FROM books {filt}"
            " ORDER BY category_l1, category_l2, title", args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def backfill_bigrams(db_path: str) -> None:
    """既有库迁移：填 chunks.bi 实体列（无索引开销）+ FTS 整建。

    幂等：bi='' 的块才处理。索引重建用 'rebuild'（external-content）。
    """
    init_corpus(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("PRAGMA temp_store=MEMORY")
        # 旧版 chunks_bi（无 content= 的普通表）无法 rebuild，弃之重建
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='chunks_bi'"
        ).fetchone()
        if ddl and "content=" not in ddl[0]:
            print("旧二元索引（普通表）弃置重建...", flush=True)
            conn.execute("DROP TABLE chunks_bi")
            conn.execute(
                "CREATE VIRTUAL TABLE chunks_bi USING fts5("
                "bi, content='chunks', content_rowid='id',"
                " tokenize='unicode61')")
            conn.commit()
        done = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE bi != ''").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        print(f"bi 列填充：{done}/{total}", flush=True)
        while True:
            rows = conn.execute(
                "SELECT id, text FROM chunks WHERE bi = '' LIMIT 50000"
            ).fetchall()
            if not rows:
                break
            with conn:
                conn.executemany(
                    "UPDATE chunks SET bi=? WHERE id=?",
                    [(_bigrams(t), cid) for cid, t in rows])
            done += len(rows)
            print(f"  bi 列 {done}/{total}", flush=True)
        print("整建二元索引（rebuild，C 层批量）...", flush=True)
        conn.execute("DELETE FROM chunks_bi")
        conn.execute("INSERT INTO chunks_bi(chunks_bi) VALUES('rebuild')")
        conn.commit()
        print("二元索引整建完成", flush=True)
    finally:
        conn.close()


def repair_corpus(source_db: str, target_db: str, source_root: str,
                  report_path: str) -> dict:
    """在线备份后修复书目；源库只读，目标库必须不存在。"""
    import json

    source = Path(source_db).resolve()
    target = Path(target_db).resolve()
    root = Path(source_root).resolve()
    report_file = Path(report_path)
    if target.exists():
        raise FileExistsError(f"目标库已存在: {target}")
    if source == target:
        raise ValueError("目标库不得与源库相同")
    target.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(root.rglob("*.txt"))

    old = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    new = sqlite3.connect(target)
    try:
        old.backup(new)
    finally:
        old.close()
        new.close()

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    report = {
        "source_txt": len(files),
        "before_books": 0,
        "after_books": 0,
        "expected_nonempty": 0,
        "collisions": [],
        "recovered": [],
        "metadata_changes": [],
        "anomalies": [],
        "failures": [],
        "validation": {},
    }
    try:
        rows = conn.execute("SELECT * FROM books").fetchall()
        report["before_books"] = len(rows)
        by_path = {str(Path(r["path"]).resolve()).casefold(): r for r in rows}
        expected_paths = set()
        expected_hashes = {}
        expected_empty = 0
        updates = []
        recoveries = []
        for path in files:
            rel = path.relative_to(root)
            parts = rel.parts[:-1]
            l1 = parts[0] if parts else ""
            l2 = parts[1] if len(parts) > 1 else ""
            key = str(path.resolve()).casefold()
            expected_paths.add(key)
            text, _ = _read_text(path)
            expected_hashes[key] = hashlib.sha256(
                text.encode("utf-8")).hexdigest()
            if not _chunk(text)[0]:
                expected_empty += 1
            title, dynasty, author, metadata_note = _parse_metadata(path.name, l2)
            if metadata_note:
                report["anomalies"].append(
                    {"path": str(path), "reason": metadata_note})
            existing = by_path.get(key)
            if existing is not None:
                changed = {
                    field: {"before": existing[field], "after": value}
                    for field, value in (("title", title), ("dynasty", dynasty),
                                         ("author", author))
                    if existing[field] != value
                }
                notes = [n for n in existing["note"].split()
                         if n != "metadata_unresolved"]
                if metadata_note:
                    notes.append(metadata_note)
                note = " ".join(notes)
                if changed or note != existing["note"]:
                    updates.append((title, dynasty, author, l1, l2, note,
                                    existing["book_id"]))
                if changed:
                    report["metadata_changes"].append(
                        {"path": str(path), "book_id": existing["book_id"],
                         "changes": changed})
                continue

            base_id = re.sub(r"\W+", "_", path.stem)
            collision = conn.execute(
                "SELECT path FROM books WHERE book_id=?", (base_id,)).fetchone()
            if collision:
                report["collisions"].append(
                    {"base_id": base_id, "existing_path": collision["path"],
                     "recovered_path": str(path)})
            entry = {"path": str(path), "book_id": _book_id(conn, path),
                     "chunks": 0, "chars": 0}
            report["recovered"].append(entry)
            recoveries.append((path, l1, l2, entry))

        report["phase"] = "preflight"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        with conn:
            conn.executemany(
                "UPDATE books SET title=?, dynasty=?, author=?, category_l1=?,"
                " category_l2=?, note=? WHERE book_id=?", updates)
        for path, l1, l2, entry in recoveries:
            try:
                result = ingest_book(str(target), str(path), l1, l2)
                if result["status"] == "failed":
                    report["failures"].append(
                        {"path": str(path), "reason": result["note"]})
                    report["recovered"].remove(entry)
                else:
                    entry.update(chunks=result["chunks"], chars=result["chars"])
            except Exception as exc:
                report["failures"].append(
                    {"path": str(path), "reason": f"{type(exc).__name__}: {exc}"})
                report["recovered"].remove(entry)

        current_rows = conn.execute("SELECT * FROM books").fetchall()
        current_by_path = {
            str(Path(r["path"]).resolve()).casefold(): r for r in current_rows}
        report["after_books"] = len(current_rows)
        report["expected_nonempty"] = len(files) - expected_empty
        paths_match = set(current_by_path) == expected_paths
        hashes_match = paths_match and all(
            current_by_path[key]["content_hash"] == digest
            for key, digest in expected_hashes.items())

        conn.execute("ATTACH DATABASE ? AS original", (str(source),))
        chunk_columns = "id, book_id, seq, chapter, section, heading_path, text, bi"
        old_chunk_delta = conn.execute(
            "SELECT COUNT(*) FROM original.chunks o LEFT JOIN main.chunks n"
            " ON n.id=o.id WHERE n.id IS NULL OR "
            + " OR ".join(f"n.{col} != o.{col}"
                          for col in chunk_columns.split(", ")[1:])
        ).fetchone()[0]
        old_book_delta = conn.execute(
            "SELECT COUNT(*) FROM original.books o LEFT JOIN main.books b"
            " ON b.book_id=o.book_id WHERE b.book_id IS NULL OR b.path!=o.path"
            " OR b.chunk_count!=o.chunk_count OR b.char_count!=o.char_count"
        ).fetchone()[0]
        conn.execute("DETACH DATABASE original")
        search_counts = {
            query: len(search(str(target), query)["hits"])
            for query in ("茶肆", "皇城司", "夜市")
        }
        report["phase"] = "validated"
        report["validation"] = {
            "paths_match": paths_match,
            "content_hashes_match": hashes_match,
            "old_chunks_preserved": old_chunk_delta == 0,
            "old_book_metrics_preserved": old_book_delta == 0,
            "empty_count_matches": stats(str(target))["empty"] == expected_empty,
            "search_counts": search_counts,
            "no_failures": not report["failures"],
        }
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        if not all(value for key, value in report["validation"].items()
                   if key != "search_counts"):
            raise RuntimeError(f"修复校验失败，源库未修改: {report_file}")
        return report
    finally:
        conn.close()


def stats(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        chars = conn.execute(
            "SELECT COALESCE(SUM(char_count),0) FROM books").fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM books WHERE note LIKE 'failed%' OR"
            " note LIKE '%编码不可识别%'").fetchone()[0]
        empty = conn.execute(
            "SELECT COUNT(*) FROM books WHERE ' ' || note || ' '"
            " LIKE '% empty %'").fetchone()[0]
        return {"books": books, "chunks": chunks, "chars": chars,
                "failed": failed, "empty": empty}
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "search"
    if cmd == "ingest":
        r = ingest_book(sys.argv[2], sys.argv[3], *(sys.argv[4:] or []))
        print(r)
    elif cmd == "search":
        for h in search(sys.argv[2], sys.argv[3])["hits"]:
            print(f"--- {h['title']} {h['heading_path']} 第{h['seq']}块 ---")
            print(h["snip"].replace("\n", "")[:200])
    elif cmd == "stats":
        print(stats(sys.argv[2]))
