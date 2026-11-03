# 开源组件位置

自 019 起，运行组件统一在仓库内由 uv workspace 管理：

- `packages/worldseed`：WorldSeed，上游与补丁见包内 `UPSTREAM.md`。
- `packages/gptr-mcp`：调研 MCP，来源见包内 `UPSTREAM.md`。
- `packages/gpt-researcher`：GPT-Researcher，来源与本地调整见包内 `UPSTREAM.md`。
- `plugins/gptr-deepseek-retriever`：DeepSeek 检索插件。

历史外部目录仅用于追溯，不再是安装或运行依赖。LiteRT-LM 与模型文件仍属外部运行资源，位置由 `LITERT_LM` 和 `EMBEDDING_MODEL_FILE` 配置。
