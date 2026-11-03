# WorldSeed 来源记录

- 上游仓库：https://github.com/World-AI-Team/WorldSeed （当前镜像：https://gitcode.com/gh_mirrors/wo/WorldSeed.git）
- 上游基线：`4ffeabfdee6dbeb1cb248bf676ad13667b22d359`
- 收拢日期：2026-11-03
- 许可证：MIT，见 `LICENSE`
- 收拢范围：运行所需 `src/`、`shared/`、`configs/` 与包定义；不包含上游前端、虚拟环境和开发工作文件。
- 本地修改：`src/worldseed/dm/prompt.py` 与 `src/worldseed/scene/config.py` 的 3 行显式 UTF-8 读取补丁，原补丁留档于 `docs/worldseed-local-patch/locale-encoding.patch`；移除上游独立开发依赖组，测试工具由根 workspace 统一解析。
