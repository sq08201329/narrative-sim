# Contract: 古籍书目无损修复

## 入库标识

`ingest_book(db_path, txt_path, category_l1="", category_l2="")` 保持既有签名和返回
状态。相同路径始终映射到同一 ID；不同路径即使同名或同内容也不得覆盖。

## 元数据解析

内部解析以路径和两级目录分类为证据，返回 `title / dynasty / author` 及可选异常注记。
不调用外部服务。朝代和作者无可靠证据时为空字符串，书名至少保留去除扩展名后的
原始有效文本，不得返回空书名。

## 修复接口

文库入口提供：

- `repair_corpus(source_db, target_db, source_root, report_path) -> dict`
  - `source_db` 只读，`target_db` 必须不存在。
  - 通过在线备份创建目标库，再修复元数据和缺失 TXT。
  - 写 JSON 报告并完成校验；失败抛出异常，不修改源库。
- CLI：`uv run python scripts/corpus_repair.py ROOT --db data/corpus.db`
  默认仅生成候选库和报告；`--apply` 在校验成功后才原子替换，并打印唯一回滚路径。

## 不变量

1. 目标库书目路径集合与源目录 TXT 全集相同。
2. 每条书目内容哈希与源文件解码归一后的哈希相同。
3. 源库全部旧块在目标库逐字段保持；既有未冲突 ID 不变。
4. 不覆盖任何既有备份；应用失败时生产库路径仍指向原库。
5. 报告不包含正文全文，不包含密钥或外部服务信息。
