# GPT-Researcher 来源记录

- 上游项目：https://github.com/assafelovic/gpt-researcher.git
- 当前来源镜像：https://gitcode.com/GitHub_Trending/gp/gpt-researcher.git
- 固定基线：`27c0f42b08c9016b266c432a9f5a5f4fd1e8b3b1`
- 收拢日期：2026-11-03
- 许可证：MIT，见 `LICENSE`
- 收拢原因：PyPI 0.16.0 的 `query_processing.py` 缺少 typing 导入，且上述镜像提交无法由 uv 拉取；当前源码副本包含既有调研链路所需修复。
- 收拢范围：`gpt_researcher/` 运行包、包定义、README 与许可证；不包含上游虚拟环境、测试缓存和开发工作文件。
- 本地调整：移除包内自引用的 `[tool.uv.sources]`，由根 workspace 统一管理；移除运行源码未使用的 `mcp<2` 依赖，避免与项目现有 MCP 2.x 冲突。
