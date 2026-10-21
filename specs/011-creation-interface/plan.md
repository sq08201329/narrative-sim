# Implementation Plan: 创作队对接接口

**Branch**: `011-creation-interface` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-creation-interface/spec.md`

## Summary

把创作 agent team 的对接面补齐：MCP 新增 7 个读工具 + 修订/回滚/移交/重拍
4 个写工具 + 既有工具扩参（run_simulation 加 dm 开关、research_brief 进 MCP）。
核心新逻辑只有两块：`asset_revisions` 版本化存储（orchestrator/revision.py +
store 原语）与移交包导出（orchestrator/handoff.py）；其余全部是 store 既有方法的
MCP 薄透传。污染防线靠三冻结面（原料表/事件表/世界 config）+ 修订只进叠加层。

## Technical Context

**Language/Version**: Python 3.12（requires-python >=3.12）

**Primary Dependencies**: 零新增（fastmcp-slim 007 已引入；移交包用 stdlib
json/hashlib/pathlib）

**Storage**: SQLite 经 store.py 唯一入口；新增 `asset_revisions` 表 +
`assets.current_revision` 列（init_db 幂等迁移老库）

**Testing**: pytest 离线契约测试；MCP 工具经 fastmcp Client 直连（007 既有
测试模式）；零外部调用

**Target Platform**: Windows 本机，MCP streamable-http 127.0.0.1:8300

**Project Type**: cli/library + MCP server

**Performance Goals**: 非性能特性；移交包导出为一次性批量读

**Constraints**: 宪章 II（MCP 只封装）、III（store 单写）、IV（离线 Mock 基线）

**Scale/Scope**: 单库、个位数 world、百级资产、千级事件的量级

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 依据 |
|------|------|------|
| I. 契约先行 | PASS | contracts/mcp-tools.md 先行定义 11 个新工具签名与错误词汇表 |
| II. 单一胶水层 | PASS | 新逻辑落 orchestrator/revision.py 与 handoff.py；mcp_server 只透传 |
| III. 存储单一入口 | PASS | asset_revisions 读写全部经 store.py 新原语；init_db 迁移 |
| IV. 适配器隔离与 Mock 基线 | PASS | 读/修订/移交/重拍全部离线可测（mock 后端）；无新外部服务 |
| V. UV 统一依赖 | PASS | 零新增包 |
| VI. 密钥与成本边界 | PASS | research_brief/run_simulation(dm) 的工具 docstring 标注成本量级 |
| VII. 一特性一分支 | PASS | 011-creation-interface |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/011-creation-interface/
├── plan.md              # 本文件
├── research.md          # Phase 0：修订存储/并发/冲突警告/重拍语义等决策
├── data-model.md        # Phase 1：asset_revisions 表 + 世界 config 扩展 + 移交目录
├── quickstart.md        # Phase 1：离线验证 + 真机联调步骤
├── contracts/
│   └── mcp-tools.md     # Phase 1：11 个新工具契约 + 错误词汇表
└── tasks.md             # /skill:speckit-tasks 产出
```

### Source Code (repository root)

```text
orchestrator/
├── revision.py          # 新增：修订/回滚业务（merge patch、乐观锁、使用警告）
├── handoff.py           # 新增：移交包导出（manifest + 各内容文件）
├── store.py             # 修改：revision 原语（put/get/list_revision、
│                        #   current_revision 指针）、put_asset 自动 revision 0
├── mcp_server.py        # 修改：11 个新工具薄封装 + run_simulation dm 参数
└── world.py             # 修改：build_scene_config 支持 revision pin 取卡

db/
└── init_db.py           # 修改：asset_revisions 表 + assets.current_revision
│                        #   幂等迁移（PRAGMA table_info + ALTER）

tests/contract/
├── test_revision.py     # 新增：修订/回滚/污染防线/并发冲突
├── test_handoff.py      # 新增：移交包结构与 manifest 自描述
└── test_mcp_server.py   # 修改：新读工具契约
```

**Structure Decision**: 单项目布局；新业务模块仅 revision.py 与 handoff.py
两个，其余为既有文件增量。

## 设计要点（Phase 1 摘要）

1. **修订存储**：`asset_revisions(asset_id, revision, payload 完整快照, patch,
   reason, author, created_at)`，UNIQUE(asset_id, revision)；`assets` 加
   `current_revision` 指针列。revise = merge patch → 快照入修订表 → 指针前移；
   rollback = 指针回指 + payload 回填快照。revision 0 由 put_asset 首建时自动
   写入（author=调研 retriever 标签），永不改删。
2. **版号锚点**：create_world 冻结 config 增加 `revisions: {asset_id: rev}`；
   run_simulation 按 pin 取卡（build_scene_config 新增 pins 参数，None = 现状
   兼容旧库）；reshoot(use_latest=True) 重新钉版后跑新 run。
3. **冲突警告**：revise 响应带 impacted_runs（引用过该资产的 run/world 列表 +
   各自冻结版号）——留痕型警告，不做语义判断（research.md R3）。
4. **并发**：revise_asset(patch, base_revision) 乐观锁——base 与当前指针不符
   返回 RevisionConflict。
5. **移交包**：`handoff/<world_id>/` 下 manifest.json（版本/计数/sha256/版号
   锚点/密级说明）+ assets/*.json + events.jsonl + world.json + dm_calls.json
   + materials/*.md + sources.md；out_dir 已存在默认拒绝（overwrite=True 才覆盖）。
6. **错误词汇表**：AssetNotFound / RunNotFound / WorldNotFound /
   RevisionNotFound / RevisionConflict / HandoffExists —— 沿用 007
   ToolError("类型: 原因") 口径。

## Constitution Check（Phase 1 复审）

契约文件先行（I）；新逻辑收拢在两个 orchestrator 模块、MCP 零业务（II）；
修订读写唯一入口 store（III）；全部离线可测（IV）；零新依赖（V）；成本标注
进 docstring（VI）；分支隔离（VII）。**全部 PASS。**
