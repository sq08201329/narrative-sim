# Tasks: 创作队对接接口（读取 + 修订版本化 + 移交包 + 重拍）

**Input**: Design documents from `/specs/011-creation-interface/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅、data-model.md ✅、
contracts/mcp-tools.md ✅、quickstart.md ✅

**Tests**: 本特性包含测试任务 —— spec FR-015 与宪章 IV 要求离线零外部调用、
既有 141 项无回归。测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；`orchestrator/store.py` 与
`orchestrator/mcp_server.py` 被多阶段触碰，同文件任务严格串行。

## Phase 1: Setup（表与迁移）

- [x] T001 `db/init_db.py`：`asset_revisions` 幂等 DDL（UNIQUE(asset_id,
  revision) + idx_revisions_asset 索引，结构见 data-model.md）+
  `assets.current_revision INTEGER NOT NULL DEFAULT 0` 列的幂等迁移
  （PRAGMA table_info 检测，老库 ALTER TABLE ADD COLUMN）

---

## Phase 2: Foundational（修订存储原语，阻塞全部故事）

- [x] T002 `orchestrator/store.py` 修订原语：`put_revision(asset_id, payload,
  patch, reason, author) -> int`（自动取下一版号）/ `get_revision` /
  `list_revisions`（升序）/ `get_asset_at_revision` /
  `set_current_revision`（含 payload 回填）；`put_asset` 改造：首建自动写
  revision 0（author 取 provenance.retriever 缺省 "system"），已有修订且
  payload 变化时自动升版（author="system:put_asset"，research.md R2）
- [x] T003 `tests/contract/test_revision.py` 存储层用例（真实 SQLite tmp 库）：
  rev0 自动建立 / REPLACE 变化自动升版 / 指针回填不变量
  （assets.payload == revisions[current].payload）/ 老库迁移（先建无
  current_revision 列的库再 init）

**Checkpoint**: 修订原语就绪，既有 141 项回归绿

---

## Phase 3: User Story 1 - 创作 agent 读取全部存量 (Priority: P1) 🎯 MVP

**Goal**: 7 个 MCP 读工具覆盖全读路径，结构化错误词汇

**Independent Test**: fastmcp Client 直连依次调全部读工具（quickstart 离线 5）

### Tests for User Story 1（先写，确认失败）

- [x] T004 [US1] `tests/contract/test_mcp_server.py` 追加：list_assets /
  get_asset（含 current_revision 与 secrecy 标注）/ get_materials /
  search_materials（大小写不敏感子串）/ get_events / get_world_state /
  list_dm_calls；不存在对象分别返回 AssetNotFound / RunNotFound /
  WorldNotFound；空集合语义（无快照 {tick: None}、无原料 []）

### Implementation for User Story 1

- [x] T005 [US1] `orchestrator/mcp_server.py` 实现 7 个读工具薄封装
  （契约见 contracts/mcp-tools.md 读工具节；全部为 store 方法透传 +
  ToolError 词汇表）

**Checkpoint**: US1 测试全绿 + 回归绿

---

## Phase 4: User Story 2 - 资产修订版本化与回滚 (Priority: P2)

**Goal**: revise/rollback 业务闭环 + 乐观锁 + 使用留痕警告 + 三冻结面断言

**Independent Test**: 修订→读回→回滚→读回全链；修订前后原料表/事件表/
他世界 config 逐字节不变（quickstart 离线 1-2）

### Tests for User Story 2（先写，确认失败）

- [x] T006 [US2] `tests/contract/test_revision.py` 追加业务层用例：
  revise merge patch 深合并（None 删键）/ 空 patch 与非 dict 拒绝
  （BadPatch）/ base_revision 乐观锁 RevisionConflict / impacted_runs
  反查 worlds.config pin / rollback 回填 + stale_worlds 标记 /
  RevisionNotFound / **三冻结面逐字节断言**（FR-009）
- [x] T007 [US2] `tests/contract/test_mcp_server.py` 追加：
  revise_asset / rollback_asset 经 MCP 调用与错误词汇

### Implementation for User Story 2

- [x] T008 [US2] 实现 `orchestrator/revision.py`：RevisionError 族 +
  `_merge_patch`（深合并，None 删键）+ `revise`（校验 → 合并 →
  put_revision → impacted_runs + warning 文案）+ `rollback` +
  `impacted_runs`（worlds.config revisions 反查 + run 列表）
- [x] T009 [US2] `orchestrator/mcp_server.py` 接 revise_asset /
  rollback_asset 两工具（薄封装 + 错误词汇映射）

**Checkpoint**: US2 测试全绿 + 回归绿

---

## Phase 5: User Story 3 - 素材移交包 (Priority: P2)

**Goal**: export_handoff 产出自描述移交目录

**Independent Test**: 演示库导出后仅凭 manifest 解析全部内容，sha256 实算
一致（quickstart 离线 4）

### Tests for User Story 3（先写，确认失败）

- [x] T010 [US3] `tests/contract/test_handoff.py`：目录布局齐全 /
  manifest format/counts/sha256/revision_pins/secrecy 字段 / 空世界
  events 与 dm_calls 为空数组 / 已存在拒绝覆盖（HandoffExists）与
  overwrite=True / assets 文件含 secret 且带密级标注 / materials 按资产
  分 md / sources.md 汇总 provenance 与原料来源

### Implementation for User Story 3

- [x] T011 [US3] 实现 `orchestrator/handoff.py`：export_handoff(store,
  world_id, out_dir, run_id=None, overwrite=False)（目录布局与 manifest
  字段见 data-model.md；sha256 逐文件实算；run_id 缺省取该世界最近 run）
- [x] T012 [US3] `orchestrator/mcp_server.py` 接 export_handoff 工具

**Checkpoint**: US3 测试全绿 + 回归绿

---

## Phase 6: User Story 4 - 重拍 (Priority: P3)

**Goal**: 版号锚点 + reshoot，两版 run 并存可 diff；run_simulation 加 dm 开关

**Independent Test**: 同世界原样重拍 + 修订重拍各一次，三 run 并存
event_id 零冲突（quickstart 重拍演示）

### Tests for User Story 4（先写，确认失败）

- [x] T013 [US4] `tests/contract/test_revision.py` 追加：create_world 冻结
  revisions pin / run_simulation 按 pin 取旧卡（修订后行为不变）/
  reshoot(use_latest=True) 重钉版用新卡 / 三 run event_id 全局连续零冲突 /
  reshoot 到不存在世界 WorldNotFound、run_id 冲突 RunExists /
  run_simulation dm=False 兼容锚点（007 版返回键不变）

### Implementation for User Story 4

- [x] T014 [US4] `orchestrator/world.py`：build_scene_config 增加
  `pins: dict | None` 参数（非 None 时按 get_asset_at_revision 取卡，
  None 为现状兼容）；`orchestrator/mcp_server.py`：create_world 冻结
  revisions pin / run_simulation 按 pin 传参 + dm/dm_max_calls/
  dm_knowledge_chars 参数（FR-013）/ reshoot 工具（FR-012）

**Checkpoint**: US4 测试全绿 + 回归绿

---

## Phase 7: Polish & 收尾

- [x] T015 [P] `orchestrator/mcp_server.py` 接 research_brief(theme) 工具
  （FR-014，薄封装 orchestrator/brief.py generate_brief + execute_brief，
  docstring 标注成本量级）；离线 mock 接缝测试
- [x] T016 全量回归 `uv run pytest -m "not real" -q` 全绿；真机冒烟
  （quickstart 真机联调：NARRATIVE_DB=yanyu.db 起服务，读路径 + 修订 +
  移交包）
- [x] T017 标记 tasks.md 全部 [X]；提交

---

## Dependencies & Execution Order

- Phase 1 → 2 → US1 → US2 → US3 → US4 → Polish，严格串行（store.py 与
  mcp_server.py 为共享文件）
- 可并行：T015 相对独立（brief.py 既有能力透传），但同文件故排 Polish

## Implementation Strategy

MVP = Phase 1-3（US1 读接口）：创作 agent 接入的最低可用集。
US2 叠加修订版本化（创作队动工前提），US3 移交包收口交付，US4 重拍打磨，
Polish 补齐 research_brief 与真机冒烟。
