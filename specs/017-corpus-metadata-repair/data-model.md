# Data Model: 古籍书目无损修复

## books（既有实体，不增列）

- `book_id`: 主键。未冲突记录保持原值；冲突新增记录为可读基础名加路径哈希后缀。
- `title / dynasty / author`: 可修正的规范字段；无可靠证据时后两者为空。
- `category_l1 / category_l2`: 来源目录分类，同时作为丛书前缀匹配证据。
- `path`: 完整原始来源路径；文件名与目录事实均由此保留。
- `content_hash`: 解码归一后的正文 SHA-256；用于逐路径验收和幂等。
- `chunk_count / char_count`: 既有记录迁移前后不变；恢复记录按正文生成。
- `note`: 保留既有编码、空书及分块注记，可追加 `metadata_unresolved`。

## chunks / chunks_fts / chunks_bi（既有实体）

- 共同书目的 `id / book_id / seq / chapter / section / heading_path / text / bi`
  必须逐字段不变。
- 仅为源目录存在而当前库缺失的书目新增块及索引项。

## 修复报告（JSON 文件，不入库）

- `source_txt / before_books / after_books / expected_nonempty`
- `collisions`: 同基础 ID 的来源路径及最终 ID。
- `recovered`: 新恢复路径、书目 ID、块数、字数。
- `metadata_changes`: 路径、前后书名/朝代/作者。
- `anomalies`: 无法可靠解析的路径和原因。
- `validation`: 路径覆盖、内容哈希、旧块保持、空书和检索检查结果。

## 状态流

`盘点 → 备份新库 → 修复新库 → 校验通过 → 显式应用 → 保留唯一回滚副本`

任何校验失败停留在新库，不替换生产库。
