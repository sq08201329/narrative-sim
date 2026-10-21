# Tasks: 角色参考图生成（MiniMax image-01）

**Input**: Design documents from `/specs/013-reference-images/`

**Prerequisites**: plan.md ✅、spec.md ✅、research.md ✅、data-model.md ✅、
contracts/images.md ✅、quickstart.md ✅

**Tests**: 本特性包含测试任务 —— spec FR-009 与宪章 IV 要求离线零外部调用、
既有 188 项无回归。测试任务先写并确认失败，再实现。

**Organization**: 按用户故事分阶段；`orchestrator/store.py`、
`orchestrator/mcp_server.py`、`orchestrator/handoff.py` 为共享文件严格串行。

## Phase 1: Setup

- [ ] T001 [P] `db/init_db.py`：`image_generations` 幂等 DDL（结构见
  data-model.md，含 idx_image_gen_asset 索引）
- [ ] T002 [P] `.gitignore` 增加 `images/` 与 `handoff/`；`.env.example`
  增加 `MINIMAX_API_KEY=` 与 `MINIMAX_BASE_URL`（注释含获取入口）

---

## Phase 2: Foundational（存储原语）

- [ ] T003 `orchestrator/store.py`：`put_image_generation(asset_id, prompt,
  n, aspect_ratio, paths, sha256, provider, asset_revision) -> int` /
  `list_image_generations(asset_id) -> list[dict]`
- [ ] T004 `tests/contract/test_images.py` 存储用例：写读往返 / 多记录 /
  空返回 []

**Checkpoint**: 原语就绪，既有 188 项回归绿

---

## Phase 3: User Story 1 - 一键生成参考图 (Priority: P1) 🎯 MVP

**Goal**: mock provider 驱动全链（落盘 + 登记 + 修订留痕 + 原子性）

**Independent Test**: 假 PNG 字节全流程断言（quickstart 离线 1-4）

### Tests for User Story 1（先写，确认失败）

- [ ] T005 [US1] `tests/contract/test_images.py` 主体：mock provider 全链
  （文件落盘 images/<asset_id>/<sha12>.png、reference_images 追加相对路径、
  资产修订 +1、生成记录字段齐）/ BadPrompt（无 prompt 无 override）/
  失败原子性（provider 抛错 → 零文件零字段零记录）/ 宽高比默认
  （character 2:3、scene 16:9、显式优先）/ 同内容去重同名不覆盖 /
  n=2 多张全登记

### Implementation for User Story 1

- [ ] T006 [US1] 实现 `orchestrator/images.py`：ImageGenError +
  ImageProvider 协议 + generate_reference_images（R4 原子次序：
  取字节 → 校验 → 写盘 → put_asset → put_image_generation）
- [ ] T007 [US1] `orchestrator/images.py` 实现 MinimaxImageProvider
  （POST /v1/image_generation，base64 优先、image_urls 回退下载，
  base_resp.status_code != 0 → ImageGenError(status_msg)，缺 key 指明
  键名；httpx 直调，R5）

**Checkpoint**: US1 离线全绿 + 回归绿

---

## Phase 4: User Story 2 - 提示词可控 (Priority: P2)

**Goal**: prompt_override 覆盖与留痕对照

**Independent Test**: 覆盖值出现在生成记录与 provider 收到的入参

### Tests for User Story 2（先写，确认失败）

- [ ] T008 [US2] `tests/contract/test_images.py` 追加：prompt_override
  时 provider 收到覆盖值且记录留痕；未覆盖时记录与资产 visual_prompt
  一致

### Implementation for User Story 2

- [ ] T009 [US2] 若 T008 暴露缺口则修补（预期零代码：T006 契约已含
  override；本任务兜底）

**Checkpoint**: US2 测试全绿

---

## Phase 5: User Story 3 - 移交包带图 (Priority: P3)

**Goal**: handoff 加 images/ 目录 + manifest 登记

**Independent Test**: 带图世界导出，manifest 图片条目 sha256 与实算一致
（SC-004）

### Tests for User Story 3（先写，确认失败）

- [ ] T010 [US3] `tests/contract/test_handoff.py` 追加：带图资产移交
  （images/ 含图 + manifest 条目 sha256 一致 + counts 增 images 键）/
  无图资产跳过不报错

### Implementation for User Story 3

- [ ] T011 [US3] `orchestrator/handoff.py`：遍历世界资产 reference_images
  复制图片（复用 _write 登记哈希）；counts 增 images

**Checkpoint**: US3 测试全绿 + 回归绿

---

## Phase 6: Polish & 真机验收

- [ ] T012 `orchestrator/mcp_server.py` 接 generate_reference_image 工具
  （契约 §3，错误词汇 AssetNotFound/BadPrompt/ImageGenError）+
  `test_mcp_server.py` 契约用例 + EXPECTED_TOOLS 更新
- [ ] T013 全量回归 `uv run pytest -m "not real" -q` 全绿
- [ ] T014 真机验收（quickstart）：yanyu.db 察子生成 1 张竖版（2:3），
  图片可打开且语义相符（人工核对）；错误密钥故障验证（零残留）
- [ ] T015 标记 tasks.md 全部 [X]；提交

---

## Dependencies & Execution Order

- Phase 1 → 2 → US1 → US2 → US3 → Polish，严格串行
- 可并行：T001 ∥ T002

## Implementation Strategy

MVP = Phase 1-3（US1）：单资产出图全链。US2 提示词增强，US3 移交收口，
Polish 接 MCP 与真机出图验收。
