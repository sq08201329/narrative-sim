# Phase 0 Research: 可迁移运行时

## WorldSeed 收拢范围

- **Decision**: 在 `packages/worldseed` 保存上游 `4ffeabfdee6dbeb1cb248bf676ad13667b22d359` 的 `src/`、`shared/`、`configs/`、pyproject、README 与 MIT LICENSE，并应用现有 3 行 UTF-8 补丁。
- **Rationale**: 运行时代码会从包根读取 `shared/languages.json`，场景预设位于 `configs/`；只复制 `src/` 会造成隐性缺料。
- **Alternatives considered**: 保留本机 editable path（不可迁移）；PyPI worldseed（是不同发行版）；复制完整工作副本（包含无关前端、缓存和认知文件）。

## gptr-mcp 收拢与依赖环境

- **Decision**: 在 `packages/gptr-mcp` 保存上游 `63884773685b1f12c7f0d9e283b3d71a5b9b5fda` 的 server/utils/README/MIT LICENSE，新增 uv 包定义；根项目依赖该成员，以其 `server.py` 在根环境启动。
- **Rationale**: 消除第二个 venv，同时让 GPT-Researcher 及插件进入同一锁文件。依赖使用现有 `fastmcp-slim[server]`，避免再引入另一套 FastMCP 发行包。
- **Alternatives considered**: 保留 gptr 独立 venv（换机仍需手工建环境）；仅复制脚本但不声明依赖（不可复现）；引入完整 fastmcp 包（与 slim 发行形态冲突）。

## GPT-Researcher 可用来源

- **Decision**: 将当前镜像 commit `27c0f42b08c9016b266c432a9f5a5f4fd1e8b3b1` 的运行包收拢到 `packages/gpt-researcher`，作为第三个 workspace 成员。
- **Rationale**: PyPI 0.16.0 缺少 typing 导入且无法启动；镜像 commit 包含修复但 uv 无法拉取。本地收拢同时保留可复现性与现有行为。运行源码未使用 `mcp<2`，本地包移除该冲突依赖。
- **Alternatives considered**: 使用 PyPI（导入失败）；固定镜像 Git（fetch 失败）；升级根项目以外的第二环境（违背统一环境目标）。

## 数据目录

- **Decision**: `NARRATIVE_HOME` 默认仓库根；默认剧目库 `<home>/data/projects/linan.db`、调研主库 `<home>/data/library.db`、古籍库 `<home>/data/corpus.db`；三个独立覆盖分别为 `NARRATIVE_DB`、`LIBRARY_DB`、`CORPUS_DB`。
- **Rationale**: 符合既有三库职责，又使整组运行数据可随一个根目录迁移；旧库不自动移动。
- **Alternatives considered**: 合并数据库（违反职责分离）；继续古籍固定相对 cwd（HOME 不覆盖完整数据）；立即改用系统用户目录（会改变当前默认数据集）。

## 嵌入运行时与模型

- **Decision**: `LITERT_LM` 可为可执行文件路径或 PATH 名称；`EMBEDDING_MODEL_FILE` 指向本地模型，默认 `models/model.litertlm`；模型名继续用 `EMBEDDING_MODEL`。启动前检查文件，存在且未导入时自动导入。
- **Rationale**: 文件配置比目录配置更明确，模型可放任意磁盘；仓库只保留路径示例，不包含权重。
- **Alternatives considered**: 保留 EMBEDDING_ROOT 本机路径（不可迁移）；自动下载器（超出范围且增加网络/校验复杂度）。

## 兼容脚本与验证

- **Decision**: `scripts/start_stack.ps1` 保留 Action/DbPath 参数，但转为调用统一 CLI；干净副本排除 `.git`、`.env`、虚拟环境、数据库、日志和模型后执行安装及离线验收。
- **Rationale**: 同一服务逻辑只有一份，验证不接触真实密钥和数据。
- **Alternatives considered**: 保留两套服务管理（会继续漂移）；直接依赖原机器目录做验收（无法证明迁移性）。

所有未知项均已解决，无 NEEDS CLARIFICATION。
