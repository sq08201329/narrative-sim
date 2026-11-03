# Init Contract

```text
narrative [--home PATH] init
NarrativeSim.exe [--home PATH] init
```

成功输出 data-model.md 定义的 JSON。重复执行返回全部 existing，内容不变。命令无 `--force`，不启动服务、不下载模型、不修改数据库。

`start` 调用同一初始化实现，但不要求用户预先执行 init。发行包根目录同时提供 `.env.example`，只读资源中保留技能模板。
