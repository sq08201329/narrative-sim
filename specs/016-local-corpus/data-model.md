# Data Model: 古籍文库

**Date**: 2026-10-25 | **Feature**: 016-local-corpus

## schema v2（db/corpus.py，对 spike 破坏性升级——spike 库重入即可）

### books

| 列 | 类型 | 说明 |
|----|------|------|
| book_id | TEXT PRIMARY KEY | 文件名规范化 |
| title | TEXT NOT NULL | 书名（文件名解析） |
| dynasty | TEXT | 朝代（可空） |
| author | TEXT | 作者（可空） |
| category_l1 | TEXT | 藏（史藏/子藏…，目录第一层） |
| category_l2 | TEXT | 类（正史/地理…，目录第二层） |
| path | TEXT NOT NULL | 源文件绝对路径（只读引用） |
| content_hash | TEXT NOT NULL | UTF-8 正文 sha256（幂等锚） |
| chunk_count | INTEGER NOT NULL | 块数 |
| char_count | INTEGER NOT NULL | 字数 |
| note | TEXT NOT NULL DEFAULT '' | empty / no_punct_fallback / 失败原因 |
| ingested_at | TEXT NOT NULL DEFAULT (datetime('now')) | |

### chunks

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | |
| book_id | TEXT NOT NULL REFERENCES books(book_id) | |
| seq | INTEGER NOT NULL | 书内序号 |
| chapter | TEXT NOT NULL DEFAULT '' | 卷（如"卷十六"） |
| section | TEXT NOT NULL DEFAULT '' | 篇目（如"茶肆"） |
| heading_path | TEXT NOT NULL DEFAULT '' | "卷十六 > 茶肆" |
| text | TEXT NOT NULL | 原文（UTF-8，不动一字） |

索引：idx_chunks_book(book_id)；FTS5：`chunks_fts(text, content='chunks',
tokenize='trigram')`（同 spike）。

## 古籍原料（复用戏库 research_materials，零 schema 变更）

- `retriever` = `corpus:<book_id>·<heading_path>`
- `context` = 原文块 + "\n\n【现代汉语转写】\n" + 转写
- `query` = 调研 query（009 精确缓存/漏斗天然复用）

## 移交与共享

- corpus.db 为全项目共享只读语料，**不进任何戏的移交包**（移交包只带
  该戏落库的原料条目——其中古籍来源的原料已在 context/retriever 里
  带足出处）。
