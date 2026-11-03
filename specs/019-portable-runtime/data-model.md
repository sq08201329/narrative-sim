# Data Model: 可迁移运行时

不修改业务表结构，仅定义路径与来源配置。

## ApplicationPaths

| 配置 | 优先级 | 默认值 | 用途 |
|---|---|---|---|
| home | `--home` → `NARRATIVE_HOME` | 仓库根目录 | 派生全部运行数据位置 |
| narrative_db | `--db` → `NARRATIVE_DB` | `<home>/data/projects/linan.db` | 剧目世界、运行与事件 |
| library_db | `--library-db` → `LIBRARY_DB` | `<home>/data/library.db` | 共享调研资产与原料 |
| corpus_db | `CORPUS_DB` | `<home>/data/corpus.db` | 共享古籍语料与索引 |
| logs | 由 home 派生 | `<home>/logs` | 服务日志 |
| runtime | 由 home 派生 | `<home>/run` | 受管服务状态 |

规则：路径在调用边界解析为绝对路径；覆盖任一数据库不影响其他数据库；修改路径不复制或修改旧文件。

## ExternalRuntime

| 配置 | 默认值 | 缺失行为 |
|---|---|---|
| LITERT_LM | PATH 中的 `litert-lm` | 启动前提示安装或配置该变量 |
| EMBEDDING_MODEL_FILE | `models/model.litertlm` | 模型未导入且文件缺失时明确失败 |
| EMBEDDING_MODEL | `eg2-text-270m.litertlm` | 沿用现有模型名 |
| EMBEDDING_API_BASE | 用户服务地址 | 无效时指出该配置缺失或非法 |
| GPTR_MCP_URL | 用户调研服务地址 | 无效时指出该配置缺失或非法 |

模型文件不入库；离线 Mock 工作流不读取 ExternalRuntime。

## ComponentProvenance

每个收拢组件记录：上游仓库 URL、完整上游 commit、本地修改说明、许可证文件、收拢日期。WorldSeed 的中文补丁与 `docs/worldseed-local-patch/locale-encoding.patch` 内容保持一致。
