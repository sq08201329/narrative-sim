# Feature Specification: 角色参考图生成（MiniMax image-01）

**Feature Branch**: `013-reference-images`

**Created**: 2026-10-21

**Status**: Draft

**Input**: User description: "角色参考图生成——reference_images 字段目前全空；图源用 MiniMax（key 已配）。"

## 背景与动机

资产的 `appearance.visual_prompt`（调研时生成的英文视觉描述）一直是裸文字，
`reference_images` 字段全空。下游创作环节（人物设定图、分镜、视频生成）需要
视觉锚点：一张和文字设定对齐的参考图。

图源选型已拍板：MiniMax `image-01`（云端，key 已配置；本机 ComfyUI 只有
SD1.5 级模型，古装人物质量不足，作为未来可替换的备选适配器）。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 一键为资产生成参考图 (Priority: P1)

对一个已有资产（角色/场景/道具），系统读其 visual_prompt 调用图源生成
参考图，图片落盘到资产专属目录，`reference_images` 记录文件路径，资产
因内容变化自动留下修订留痕（011 机制）。

**Why this priority**: 这是字段从"全空"到"可用"的核心链路，其余（批量、
移交）都建立在单资产生成之上。

**Independent Test**: 以 mock 图源接缝离线跑通（假图片字节落盘 +
reference_images 更新 + 修订留痕）；真机对演示库一个角色生成一张真人像。

**Acceptance Scenarios**:

1. **Given** 资产有 visual_prompt，**When** 发起生成，**Then** 图片写入
   `images/<asset_id>/`，`reference_images` 追加路径，资产修订版号 +1
   （留痕），响应含路径与哈希。
2. **Given** 资产无 visual_prompt（空串/缺失），**When** 发起生成，
   **Then** 明确报错指出缺口，不落盘、不改资产。
3. **Given** 图源服务失败（超时/鉴权失败/内容审核拦截），**When** 生成
   中断，**Then** 明确报错且不落半成品文件、不改资产字段。
4. **Given** 已生成过参考图的资产，**When** 再次生成，**Then** 追加新文件
   不覆盖旧图（版本自然堆积，创作队可挑选）。

---

### User Story 2 - 提示词可控 (Priority: P2)

默认用资产的 visual_prompt；允许调用方覆盖提示词（如创作队想强化某细节）
或追加风格后缀；实际使用的提示词随图留痕（生成记录可对照）。

**Why this priority**: 参考图质量高度依赖提示词；但默认链路（US1）已可用，
此为增强。

**Independent Test**: 覆盖提示词生成后，生成记录中的提示词与覆盖值一致。

**Acceptance Scenarios**:

1. **Given** 调用时给 prompt_override，**When** 生成，**Then** 图源收到的是
   覆盖值，且留痕记录该值。
2. **Given** 不给覆盖，**When** 生成，**Then** 用资产 visual_prompt，留痕
   可对照到资产版本。

---

### User Story 3 - 移交包带图 (Priority: P3)

011 移交包在 materials/ 旁增加 images/：每个有参考图的资产带出图片文件，
manifest 记录其哈希。

**Why this priority**: 移交闭环的最后一环；依赖 US1 有图可带。

**Independent Test**: 对有图资产导出移交包，images/ 含图片且 manifest 哈希
与文件实算一致。

**Acceptance Scenarios**:

1. **Given** 世界中资产有参考图，**When** 导出移交包，**Then** images/
   目录含图、manifest 有对应条目、sha256 一致。
2. **Given** 资产无参考图，**When** 导出，**Then** 不含该资产图片条目，
   不报错。

---

### Edge Cases

- 同一资产生成多张（n>1）：全部落盘并全部登记。
- 图片目录已存在同名文件：以内容哈希/时间戳命名，不覆盖。
- 图源返回 URL 而非字节：下载落盘，URL 有有效期（24h）必须落地为文件。
- 内容审核拦截（status_code 非零）：视为生成失败，错误消息含图源返回的
  状态说明。
- 道具/时代类资产无视觉描述习惯字段：同角色同规则（无 prompt 即报错）。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 提供参考图生成适配器：输入提示词与参数（张数、
  宽高比），输出图片字节；图源实现与调用方隔离（宪章 IV），离线测试
  以 mock 适配器驱动。
- **FR-002**: 生成入口 MUST 读资产 visual_prompt 为默认提示词，支持
  prompt_override 覆盖；无有效提示词时明确报错（BadPrompt）。
- **FR-003**: 图片 MUST 落盘到 `images/<asset_id>/`（文件名含哈希或时间戳
  防覆盖），资产 reference_images 追加相对路径；字段变更走 011 修订
  机制自动留痕（asset revision +1）。
- **FR-004**: 每次生成 MUST 落生成记录（提示词、张数、路径、sha256、
  图源标识、时间、修订版号），可审计可对照。
- **FR-005**: 生成失败 MUST 原子化：不写半成品文件、不改资产字段、错误
  消息含图源状态说明。
- **FR-006**: MCP 新增 generate_reference_image(asset_id, n, aspect_ratio,
  prompt_override) 工具；密钥只经 MINIMAX_API_KEY 环境变量（.env），
  不落代码（宪章 VI）。
- **FR-007**: 宽高比默认按资产类型：character/prop 用竖版（2:3），
  scene/epoch 用横版（16:9）；显式参数优先。
- **FR-008**: 移交包 MUST 在 images/ 目录带出参考图并在 manifest 登记
  sha256；无图资产跳过不报错。
- **FR-009**: 离线测试零外部调用；既有 188 项无回归。

### Key Entities

- **参考图文件**: `images/<asset_id>/<hash>.png`，内容可验（sha256）。
- **生成记录（image_generations）**: 资产、提示词、参数、路径、哈希、
  图源、用量、时间、资产修订版号。
- **reference_images**（既有字段）: 相对路径字符串数组。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 离线 mock 链路 100% 通过：落盘、字段更新、修订留痕、
  生成记录、失败原子性全部可断言。
- **SC-002**: 真机对一个演示角色生成 1 张参考图成功，图片可打开且与
  visual_prompt 语义相符（人工核对）。
- **SC-003**: 生成失败场景（mock 注入）零半成品文件、零字段残留。
- **SC-004**: 移交包带图完整：manifest 中图片条目 sha256 与文件实算
  一致率 100%。
- **SC-005**: 离线全绿零外部调用；既有 188 项无回归；不传图源密钥时
  报错消息指明缺哪个键。

## Assumptions

- 图源为 MiniMax image-01（POST /v1/image_generation，Bearer 鉴权，
  base_resp.status_code 非零即失败）；备选 ComfyUI 适配器不在本期。
- 图片格式 PNG；每资产每次默认 1 张（n 可调，成本按张计）。
- 提示词优化（如 minimax-h3-visual-director 技能的审美增强）不在本期
  ——visual_prompt 调研时已按视觉描述生成，够用即可。
- 批量生成（全库一键出图）不在本期；逐资产调用即可，创作队自己循环。
- 生成记录表的 token 计量不适用（图像 API 按张计），记张数即可。
