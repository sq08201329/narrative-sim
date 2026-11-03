# Implementation Plan: 初始化与使用技能分发

**Branch**: `022-init-skills` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

## Summary

在 Orchestrator 增加一个共享初始化函数，创建用户目录并仅复制缺失模板。新增 `init` 命令，start 自动初始化复用同一函数。技能模板和 `.env.example` 作为 PyInstaller 只读资源打包，冻结 init 复制到 HOME，不修改全局 Agent 配置。

## Technical Context

**Language/Version**: Python 3.12；Windows 开发版与冻结 EXE

**Primary Dependencies**: 标准库 pathlib/shutil/json；现有 runtime/CLI/PyInstaller

**Storage**: 仅文件模板与用户目录，不修改业务数据库

**Testing**: pytest 契约测试、冻结 init 与发行包资源验收、现有全量回归

**Target Platform**: Windows 10/11 x64

**Project Type**: CLI 初始化与 Agent 技能模板

**Performance Goals**: 初始化只复制缺失小文件，秒级完成

**Constraints**: 不覆盖、不联网、不启动服务、不读真实 `.env`；开发与冻结结果一致

**Scale/Scope**: 1 个 init 命令、3 个模板文件、7 类用户目录

## Constitution Check

- 不改业务 Schema 或存储入口；初始化逻辑位于 Orchestrator。通过。
- M1/Mock 和现有 MCP 不变；PyInstaller 构建仍由 uv 管理。通过。
- 真实 `.env` 不进入包，模板不复制现有密钥。通过。
- 独立分支，测试和实际冻结验收后交付。通过。

## Project Structure

```text
orchestrator/
├── init_app.py                  # 共享目录与模板初始化
└── cli.py                       # init 命令与自动初始化调用

resources/skills/narrative-sim/
└── SKILL.md                     # 项目使用技能模板

packaging/narrative.spec         # 携带 .env.example 与技能模板
scripts/build_standalone.py      # 既有目录/ZIP 构建
tests/contract/test_init_app.py
tests/integration/test_standalone_app.py
```

**Structure Decision**: 单一初始化入口和单一技能模板，不写全局 skills 配置，不增加新依赖。
