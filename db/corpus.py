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
    text         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_book ON chunks(book_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id', tokenize='trigram'
);
"""

_CHAPTER_RE = re.compile(r"卷[\s　]*[一二三四五六七八九十百〇零\d]+")
_HEADING_RE = re.compile(r"^[　\s]*(\S.{0,18}?)\s*$")
_SENT_SPLIT = re.compile(r"(?<=[。！？；])")


def init_corpus(db_path: str) -> str:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    # BOM 优先（UTF-16 藏书实测存在）；其后 UTF-8 → GB18030
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("编码不可识别（非 UTF-8/UTF-16/GB18030）")


def _parse_filename(name: str) -> tuple[str, str, str]:
    m = re.match(r"(.+?)-([^-]+)-(.+)\.txt$", name)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return name.removesuffix(".txt"), "", ""


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


def ingest_book(db_path: str, txt_path: str,
                category_l1: str = "", category_l2: str = "") -> dict:
    """单书入库（契约 §1）：幂等/失败登记/事务内 FTS 同步。"""
    p = Path(txt_path)
    title, dynasty, author = _parse_filename(p.name)
    book_id = re.sub(r"\W+", "_", p.stem)
    base = {"book_id": book_id, "chunks": 0, "chars": 0, "note": ""}
    try:
        text = _read_text(p)
    except (OSError, ValueError) as e:
        return {**base, "status": "failed", "note": str(e)}

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT content_hash FROM books WHERE book_id=?", (book_id,)
        ).fetchone()
        if row and row[0] == digest:
            return {**base, "status": "skipped"}

        blocks, no_punct = _chunk(text)
        note = "no_punct_fallback" if no_punct else ""
        if not blocks:
            note = "empty"
        with conn:  # 单书一事务：要么全进要么全滚回
            old = [r[0] for r in conn.execute(
                "SELECT id FROM chunks WHERE book_id=?", (book_id,)).fetchall()]
            if old:
                marks = ",".join("?" * len(old))
                conn.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({marks})",
                             old)
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
                    " heading_path, text) VALUES(?,?,?,?,?,?)",
                    (book_id, i, chapter, section, hp, body))
                conn.execute(
                    "INSERT INTO chunks_fts(rowid, text) VALUES(?,?)",
                    (cur.lastrowid, body))
        return {**base, "status": "ingested" if blocks else "empty",
                "chunks": len(blocks), "chars": len(text), "note": note}
    finally:
        conn.close()


def search(db_path: str, query: str, limit: int = 5,
           category_l1: str | None = None, dynasty: str | None = None,
           author: str | None = None, rerank: bool = False,
           embed=None) -> dict:
    """检索（契约 §1）：关键词主力 + 过滤 + 可选命中集精排。"""
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

        if len(query) >= 3:
            sql = (
                "SELECT c.id AS cid, c.book_id, b.title, c.seq, c.chapter,"
                " c.section, c.heading_path, c.text,"
                " snippet(chunks_fts, 0, '【', '】', '…', 32) AS snip"
                " FROM chunks_fts f JOIN chunks c ON c.id = f.rowid"
                " JOIN books b ON b.book_id = c.book_id"
                f" WHERE chunks_fts MATCH ? {filt} ORDER BY rank LIMIT ?"
            )
            rows = conn.execute(sql, [f'"{query}"', *args, 200 if rerank
                                  else limit]).fetchall()
        else:
            sql = (
                "SELECT c.id AS cid, c.book_id, b.title, c.seq, c.chapter,"
                " c.section, c.heading_path, c.text, c.text AS snip"
                " FROM chunks c JOIN books b ON b.book_id = c.book_id"
                f" WHERE c.text LIKE ? {filt} LIMIT ?"
            )
            rows = conn.execute(sql, [f"%{query}%", *args,
                                      200 if rerank else limit]).fetchall()

        hits = [dict(r) for r in rows]
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
            "SELECT COUNT(*) FROM books WHERE note='empty'").fetchone()[0]
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
