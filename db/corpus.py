"""本地文库（016 spike）：古籍入库 + FTS5 全文检索。

- 古籍 txt 多为 GB18030 编码（本藏书集实测），入库统一转 UTF-8
- 切块：按句读标点（。！？；）聚合约 500 字一块
- 检索：FTS5 trigram（≥3 字子串）；2 字词回退 LIKE（ trigram 最小 3 字）
- 独立 corpus 库（data/corpus*.db）：史料不分戏，全部戏共享
"""
import json
import re
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS books (
    book_id    TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    dynasty    TEXT,
    author     TEXT,
    collection TEXT,
    path       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL REFERENCES books(book_id),
    seq     INTEGER NOT NULL,
    text    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_book ON chunks(book_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id', tokenize='trigram'
);
"""


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
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _chunk(text: str, size: int = 500) -> list[str]:
    """按句读标点聚合切块（约 size 字）。"""
    sentences = re.split(r"(?<=[。！？；])", text)
    out, buf = [], ""
    for s in sentences:
        if len(buf) + len(s) > size and buf:
            out.append(buf)
            buf = ""
        buf += s
    if buf.strip():
        out.append(buf)
    return [c.strip() for c in out if c.strip()]


def ingest_book(db_path: str, txt_path: str, collection: str = "") -> int:
    """入库一部书（文件名解析 书名-朝代-作者）。返回块数。幂等：重入先删旧。"""
    p = Path(txt_path)
    m = re.match(r"(.+?)-([^-]+)-(.+)\.txt$", p.name)
    title, dynasty, author = (m.group(1), m.group(2), m.group(3)) \
        if m else (p.stem, "", "")
    book_id = re.sub(r"\W+", "_", p.stem)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO books VALUES(?,?,?,?,?,?)",
            (book_id, title, dynasty, author, collection, str(p)))
        old = [r[0] for r in conn.execute(
            "SELECT id FROM chunks WHERE book_id=?", (book_id,)).fetchall()]
        if old:
            conn.execute(
                f"DELETE FROM chunks_fts WHERE rowid IN "
                f"({','.join('?' * len(old))})", old)
            conn.execute("DELETE FROM chunks WHERE book_id=?", (book_id,))
        blocks = _chunk(_read_text(p))
        for i, text in enumerate(blocks):
            cur = conn.execute(
                "INSERT INTO chunks(book_id, seq, text) VALUES(?,?,?)",
                (book_id, i, text))
            conn.execute(
                "INSERT INTO chunks_fts(rowid, text) VALUES(?,?)",
                (cur.lastrowid, text))
        conn.commit()
        return len(blocks)
    finally:
        conn.close()


def search(db_path: str, query: str, limit: int = 5) -> list[dict]:
    """全文检索：≥3 字走 FTS5 trigram，否则 LIKE。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if len(query) >= 3:
            rows = conn.execute(
                "SELECT c.book_id, b.title, c.seq, c.text,"
                " snippet(chunks_fts, 0, '【', '】', '…', 32) AS snip"
                " FROM chunks_fts f JOIN chunks c ON c.id = f.rowid"
                " JOIN books b ON b.book_id = c.book_id"
                " WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                (f'"{query}"', limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT c.book_id, b.title, c.seq, c.text, c.text AS snip"
                " FROM chunks c JOIN books b ON b.book_id = c.book_id"
                " WHERE c.text LIKE ? LIMIT ?",
                (f"%{query}%", limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "search"
    if cmd == "ingest":
        n = ingest_book(sys.argv[2], sys.argv[3],
                        *(sys.argv[4:] or []))
        print(f"入库 {n} 块")
    elif cmd == "search":
        for r in search(sys.argv[2], sys.argv[3]):
            print(f"--- {r['title']} 第{r['seq']}块 ---")
            print(r["snip"].replace("\n", "")[:200])
