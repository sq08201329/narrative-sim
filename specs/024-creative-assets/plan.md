# Implementation Plan: 创作资产管理技能

**Branch**: `024-creative-assets` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

## Summary

新增独立技能 `creative-assets`，教创作团队基于时间树管理工作目录与资产。技能正文按资产管理六节展开，工作目录/命名规则作为「物理布局」一节。沿用 022 的分发机制：仓库副本 + `resources/` 只读模板 + init 复制到 HOME；冻结包经既有 `resources/` 打包携带。移交包导出时附一份同源 `WORKDIR.md`。README/手册加指针小节。本特性不改 schema、DDL、存储入口或 MCP 接口。

## Technical Context

**Language/Version**: Python 3.12，uv 管理（仅 init_app.py / handoff.py 少量改动）

**Primary Dependencies**: 标准库 pathlib/shutil/json；现有 runtime/init_app/handoff

**Storage**: 不写业务数据库；WORKDIR.md 是移交包内静态文档

**Testing**: pytest 契约测试（init 复制、不覆盖、移交包 WORKDIR.md、技能内容）+ 现有全量回归

**Target Platform**: 开发版 macOS/Windows 与冻结 EXE 一致

**Project Type**: Agent 技能模板 + 文档指针

**Performance Goals**: init 只复制缺失的小文件，秒级；移交包多写一个静态文件

**Constraints**: 不覆盖已有技能；不改 schema/DDL/MCP 接口；技能与 narrative-sim 触发边界清晰；M1 不回归

**Scale/Scope**: 2 个技能文件 + 1 个 WORKDIR.md 模板 + init 注册 1 条 + handoff 写 1 文件 + 2 处文档指针

## Constitution Check

- **I 契约先行**：不改任何 schema，纯文档/模板/薄代码扩展。通过。
- **II 单一胶水层**：WORKDIR.md 由既有 `orchestrator/handoff.py` 的 `export_handoff` 写出，无新业务逻辑、不新开 MCP 工具；init 复用 `init_app.py`。通过。
- **III 存储单一入口**：WORKDIR.md 是移交包文件系统产物，非数据库，不新增存储域。通过。
- **IV Mock 基线**：M1 与既有 mock 链路不变。通过。
- **V UV 依赖**：无新增依赖。通过。
- **VI 密钥与成本**：无 LLM 调用、无密钥读写。通过。

## Project Structure

```text
resources/skills/creative-assets/
├── SKILL.md                       # 只读模板（init/冻结复制源）
└── WORKDIR.md                     # 工作目录规范同源文本（移交包副本源）

skills/creative-assets/
└── SKILL.md                       # 仓库可编辑副本，与模板字节一致

orchestrator/
├── init_app.py                    # TEMPLATES 增加技能条目
└── handoff.py                     # export_handoff 写 WORKDIR.md 并计入 items

README.md / mydocs/叙事仿真系统开发手册.md   # 创作工作目录指针小节

tests/contract/test_creative_assets.py      # 技能/init/移交/文档守卫
tests/contract/test_handoff.py              # 增加 WORKDIR.md 断言（不破既有 counts）

specs/024-creative-assets/
├── plan.md / research.md / data-model.md / quickstart.md
├── contracts/creative-assets.md
└── tasks.md                       # /skill:speckit-tasks 输出
```

**Structure Decision**: 不新建包、不改数据库、不新增 MCP 工具；全部落在既有资源目录、init 与 handoff 两个入口及文档。

## Complexity Tracking

无宪章违例，无需记录。
