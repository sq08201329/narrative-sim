"""古籍库快速整建（HDD 优化）：顺序流式重建 + 双索引 rebuild + 换文件。

替代逐行 UPDATE 的 backfill_bigrams（随机写在 HDD 上极慢）。
做法：新文件流式写入（顺序 IO）→ chunks_fts / chunks_bi 均 'rebuild'
（external-content，C 层整建）→ os.replace 原子换库。
"""
import os
import sqlite3
import sys
import time
from pathlib import Path

from .corpus import _bigrams, init_corpus


def fast_rebuild(old_path: str, new_path: str, batch: int = 10000) -> None:
    init_corpus(new_path)
    old = sqlite3.connect(f"file:{old_path}?mode=ro", uri=True)
    new = sqlite3.connect(new_path)
    new.execute("PRAGMA synchronous=OFF")
    new.execute("PRAGMA journal_mode=MEMORY")
    new.execute("PRAGMA temp_store=MEMORY")
    t0 = time.monotonic()

    try:
        books = old.execute("SELECT * FROM books").fetchall()
        with new:
            new.executemany("INSERT OR REPLACE INTO books VALUES"
                            "(?,?,?,?,?,?,?,?,?,?,?,?)", books)
        print(f"书目 {len(books)} 部已复制", flush=True)

        cur = old.execute(
            "SELECT id, book_id, seq, chapter, section, heading_path, text"
            " FROM chunks ORDER BY id")
        total = 0
        while True:
            rows = cur.fetchmany(batch)
            if not rows:
                break
            with new:
                new.executemany(
                    "INSERT INTO chunks(id, book_id, seq, chapter, section,"
                    " heading_path, text, bi) VALUES(?,?,?,?,?,?,?,?)",
                    [(cid, bid, seq, ch, sec, hp, text, _bigrams(text))
                     for cid, bid, seq, ch, sec, hp, text in rows])
            total += len(rows)
            print(f"  chunks {total}（{time.monotonic()-t0:.0f}s）",
                  flush=True)
        print("两索引整建（rebuild）...", flush=True)
        new.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        new.execute("INSERT INTO chunks_bi(chunks_bi) VALUES('rebuild')")
        new.commit()
        print(f"整建完成，耗时 {time.monotonic()-t0:.0f}s", flush=True)
    finally:
        old.close()
        new.close()


if __name__ == "__main__":
    old_path = sys.argv[1] if len(sys.argv) > 1 else "data/corpus.db"
    new_path = sys.argv[2] if len(sys.argv) > 2 else "data/corpus_new.db"
    fast_rebuild(old_path, new_path)
    bak = old_path + ".bak"
    os.replace(old_path, bak)
    os.replace(new_path, old_path)
    print(f"已换库：{old_path}（旧库备份 {bak}）")
