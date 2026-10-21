# Research: 角色参考图生成

**Date**: 2026-10-21 | **Feature**: 013-reference-images

## R1: base64 回包直落盘，不走 URL 二次下载

- **Decision**: 请求 `response_format: "base64"`，读 `data.image_base64`
  直接解码写 PNG；若回包只有 `image_urls`（实现差异），回退 httpx 下载。
- **Rationale**: 官方文档明确 URL 默认 24 小时有效——先存 URL 再异步下载
  等于给失败埋定时炸弹；base64 一次性拿字节，落盘即永久。spec Edge Case
  "URL 需落地"由回退分支兜底。
- **证据**: MiniMax 官方/集成文档（deer-flow 设计文档、Kapon 文档）：
  `POST https://api.minimaxi.com/v1/image_generation`，
  `Authorization: Bearer $MINIMAX_API_KEY`，`base_resp.status_code != 0`
  即失败（`status_msg` 带原因，含内容审核拦截）。

## R2: 文件名 = 内容哈希前缀

- **Decision**: `<sha256[:12]>.png`；同内容重复生成天然指向同文件（去重），
  不同内容永不覆盖（spec Edge Case "同名不覆盖"）。
- **Rationale**: 比时间戳命名更可验（manifest sha256 与文件名同源）；
  比序号命名更稳（并发/重拍无竞态）。

## R3: reference_images 变更复用 011 修订机制

- **Decision**: 生成成功后 `store.put_asset(更新后的资产)`——011 已改造
  put_asset：内容变化自动升 revision（author="system:put_asset"）。
  生成记录记 `asset_revision`（变更后版号）。
- **Rationale**: 零新机制拿到"哪张图对应哪版卡"的对照链；调研原版
  （无图）永远可回滚。

## R4: 原子性次序——先字节、后写盘、最后改库

- **Decision**: provider.generate 拿全部字节 → 逐张校验非空 → 写文件 →
  put_asset + put_image_generation；任何一步抛错，前面无库变更，
  文件写盘是最后一个可失败点之前无字段修改。
- **Rationale**: FR-005"零半成品零残留"。文件已写而库失败的极端情况：
  文件留盘但未登记（无害孤儿，可手动删），反向（登记了无文件）不允许。

## R5: 不引 MiniMax SDK，httpx 直调

- **Decision**: httpx（已在锁内）裸 POST；无官方 SDK 依赖。
- **Rationale**: 单端点单用途，SDK 只增加攻击面与版本包袱；与 005
  DeepSeek 检索腿的实现风格一致（薄 HTTP 适配器）。

## 成本备注

- image-01 按张计费（ Coding Plan 内额度）；docstring 与 MCP 工具描述
  标注"n 张 = n 次计费"。批量出图显式划出本期范围（spec Assumptions）。
