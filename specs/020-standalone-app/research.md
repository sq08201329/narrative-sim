# Phase 0 Research: Windows 独立应用

## 打包形态

- **Decision**: PyInstaller onedir，单目录包含 `NarrativeSim.exe` 与 `_internal`；随后压成单顶层目录 ZIP。
- **Rationale**: 多进程、原生依赖和资源读取不适合 onefile 的重复临时解压；onedir 可直接验收目录内容。
- **Alternatives considered**: 仅 uv wheel（仍需 Python）；onefile（子进程/资源路径复杂）；Nuitka（新增不必要工具链）。

## 冻结资源根

- **Decision**: 在 store/cli/services 等已有 ROOT 边界使用 PyInstaller 的冻结资源目录；开发模式仍取仓库根。Schema、WorldSeed shared/configs、config.ini、README 和许可证作为显式 datas。
- **Rationale**: 当前代码已经以 ROOT 为资源接缝，修改少数边界即可覆盖，避免散落路径判断。
- **Alternatives considered**: 继续 `__file__` 固定仓库根（冻结后不存在）；把所有资源改成远程/用户输入（不必要）。

## 调研子进程

- **Decision**: 为 CLI 增加内部 `_gptr` 子命令，冻结后由 `sys.executable _gptr` 调用打包进来的 `server.run_server()`；PyInstaller 通过 pathex/hiddenimports 纳入 server 与 utils。
- **Rationale**: 同一 EXE 就能运行调研服务，无需第二 EXE、第二 Python 或合并两个 `_internal`。
- **Alternatives considered**: 独立 research-mcp.exe（重复运行时）；冻结后运行 server.py 源码（仍依赖 Python）；把调研服务改写进 Orchestrator（改变既有边界）。

## 动态导入与数据收集

- **Decision**: 对 GPT-Researcher 收集子模块和数据，以覆盖 retriever/skills 动态加载；对 WorldSeed/TinyTroupe 收集必要数据；实际构建后用冻结命令补缺，而不是仅验证 import。
- **Rationale**: GPT-Researcher 的检索器通过入口和名称动态发现，静态分析不足。
- **Alternatives considered**: 只收集已知 deepseek 模块（可能漏掉调用链）；复制完整仓库（含无关数据）。

## 用户目录与配置

- **Decision**: 冻结默认 HOME 为 `%LOCALAPPDATA%/NarrativeSim`，首次运行复制默认 `config.ini`；从 HOME 读取 `.env`。开发默认仍为仓库根。冻结运行 TinyTroupe 时工作目录切到 HOME，导出显式路径不受影响。
- **Rationale**: 安装目录可只读，TinyTroupe 仍能找到配置；用户数据可独立备份升级。
- **Alternatives considered**: 继续程序目录（可能不可写）；全局立即 chdir（会改变相对导出路径）；要求用户手工创建全部目录（体验差）。

## 验收

- **Decision**: 构建后仅通过复制出来的 EXE 验收帮助、离线全链、stdio MCP 和受管服务；现有开发测试继续全量运行。
- **Rationale**: 冻结缺陷必须在实际交付形态中暴露。
- **Alternatives considered**: 只 import/compile（不能发现动态资源缺失）；只测构建成功（不代表应用可用）。

所有未知项均已解决，无 NEEDS CLARIFICATION。
