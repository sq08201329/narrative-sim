# Implementation Plan: 古籍书目无损修复

**Branch**: `017-corpus-metadata-repair` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/017-corpus-metadata-repair/spec.md`

## Summary

修复 016 文库的同名 ID 覆盖和异构文件名错配。入库时以来源路径解决 ID 冲突，
元数据只按明确朝代锚点、目录丛书匹配及异常留空规则派生。生产修复采用 SQLite
在线备份生成新库，仅更新书目并为缺失 TXT 补建正文，完成逐路径哈希和旧块不变
校验后再原子换库；全程无 LLM、无新增依赖、不改源文件。

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: 零新增；标准库 sqlite3 / hashlib / pathlib / json

**Storage**: `data/corpus.db`，单一入口 `db/corpus.py`

**Testing**: pytest 离线临时文库；生产迁移前后只读校验

**Target Platform**: Windows 本机，HDD

**Project Type**: library/cli

**Performance Goals**: 顺序备份和校验优先，不重建 352 万余既有块及双索引

**Constraints**: 原目录只读；旧备份不覆盖；未冲突 ID 不变；异常不猜；离线

**Scale/Scope**: 13,409 TXT；恢复 11 条被覆盖记录；修正 13,409 条书目元数据

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 依据 |
|------|------|------|
| I. 契约先行 | PASS | 先定义修复接口与验收契约，不改资产/事件 Schema |
| II. 单一胶水层 | PASS | 无跨外部库数据流，CLI 仅调用文库入口 |
| III. 存储单一入口 | PASS | 所有 SQLite 读写集中在 `db/corpus.py` |
| IV. Mock 基线 | PASS | 临时文库离线测试，运行 M1 和全量回归 |
| V. UV 统一依赖 | PASS | 零新增依赖，全部 `uv run` |
| VI. 密钥与成本边界 | PASS | 无模型和网络调用 |
| 一特性一分支 | PASS | `017-corpus-metadata-repair` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/017-corpus-metadata-repair/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/corpus-repair.md
└── tasks.md
```

### Source Code (repository root)

```text
db/
└── corpus.py                 # 唯一 ID、保守元数据解析、备份修复与校验

scripts/
└── corpus_repair.py          # 盘点/修复/应用 CLI，无直接 SQL

tests/contract/
└── test_corpus.py            # 冲突、异构名称、迁移与检索回归
```

**Structure Decision**: 复用 016 文库域入口和测试布局；不新增存储模块或白名单例外。

## 设计要点（Phase 1 摘要）

1. **稳定 ID**：默认沿用文件名派生 ID；同 ID 已属于其他路径时，使用
   `<base>_<完整规范化路径 SHA-256 前 12 位>`。既有记录自身重跑始终沿用原 ID。
2. **元数据**：先清理两侧空白及末尾“副本”标记；仅接受唯一明确朝代段作为锚点，
   其后为作者候选；卷数尾段不参与作者。目录类名与首段丛书名规范化后完全匹配
   才移除丛书前缀。无唯一锚点或剩余结构不可靠时，只保留书名并留空朝代/作者。
3. **副本修复**：`sqlite3.Connection.backup` 复制当前库；在新库更新书目，按源目录
   补入缺失路径；元数据注记与既有编码/分块注记合并且不覆盖。
4. **报告与校验**：JSON 报告记录冲突、恢复、字段变化和异常。校验源路径全集、
   规范化文本哈希、空书数量、旧块逐字段不变及关键词检索；失败则不换库。
5. **应用**：只有显式 `--apply` 才换库；新回滚文件使用唯一时间戳名称，绝不覆盖
   `corpus.db.bak` 或任何已有文件。

## Constitution Check（Phase 1 复审）

契约、存储单一入口、离线测试、UV、零成本及分支隔离均 **PASS**；既有正文与
历史引用保护已在接口和验收契约中固定。
