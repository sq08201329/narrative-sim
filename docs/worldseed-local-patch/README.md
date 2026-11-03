# WorldSeed 中文编码补丁留档

自 019 起，WorldSeed 已收拢到 `packages/worldseed`，本目录不再用于给外部工作副本打补丁。
补丁内容已应用到收拢源码，正常安装只需在项目根目录执行 `uv sync`。

## 来源

- 上游基线：`4ffeabfdee6dbeb1cb248bf676ad13667b22d359`
- 许可证与详细来源：`packages/worldseed/UPSTREAM.md`、`packages/worldseed/LICENSE`
- 留档补丁：`locale-encoding.patch`（UTF-8，无 BOM，2 个文件 3 行）

## 修改内容

1. `src/worldseed/dm/prompt.py`：读取 `shared/languages.json` 时显式使用 UTF-8。
2. `src/worldseed/scene/config.py`：加载场景与 preset YAML 时显式使用 UTF-8。

这些修改避免 Windows 中文环境下默认 GBK 解码导致 `UnicodeDecodeError`。

## 升级时核对

升级 `packages/worldseed` 上游源码时，检查上述三处仍显式指定 UTF-8；如需重新应用，
在 `packages/worldseed` 目录执行 `git apply --check ../../docs/worldseed-local-patch/locale-encoding.patch`
前必须先确认代码上下文仍匹配。运行项目离线测试与 M1 验证，不再需要任何外部 WorldSeed 目录。
