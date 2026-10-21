# Implementation Plan: 角色参考图生成（MiniMax image-01）

**Branch**: `013-reference-images` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-reference-images/spec.md`

## Summary

为资产生成参考图，把全空的 `reference_images` 字段点亮。新增
`orchestrator/images.py`：`ImageProvider` 协议 + `MinimaxImageProvider`
（`POST /v1/image_generation`，base64 回包直落盘，绕开 URL 24h 过期坑），
生成入口读 visual_prompt（可 override）→ 落 `images/<asset_id>/<sha12>.png`
→ reference_images 追加 → 经 put_asset 自动升修订版（011 机制留痕）→
`image_generations` 生成记录落库。失败原子化：无半成品文件、无字段残留。
MCP 加 `generate_reference_image` 工具；011 移交包加 images/ 目录。

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: 零新增（httpx 已随 openai/litellm 在锁内；
dotenv 既定）

**Storage**: SQLite 经 store.py（新增 `image_generations` 表）；图片文件落
`images/`（加入 .gitignore）

**Testing**: pytest 离线契约测试（mock provider 注入假字节），真机标 real

**Target Platform**: Windows 本机 + MCP streamable-http

**Project Type**: cli/library + MCP server

**Performance Goals**: 非性能特性；单张生成秒级~十秒级

**Constraints**: 失败原子化（无半成品）；密钥只经环境变量；离线零外部调用

**Scale/Scope**: 百级资产 × 个位数张图

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 依据 |
|------|------|------|
| I. 契约先行 | PASS | contracts/images.md 先行定义适配器协议/生成入口/MCP 工具 |
| II. 单一胶水层 | PASS | 新逻辑收拢 orchestrator/images.py；MiniMax 接触面只此一处 |
| III. 存储单一入口 | PASS | 生成记录与 reference_images 变更全经 store.py |
| IV. 适配器隔离与 Mock 基线 | PASS | ImageProvider 协议 + mock provider 离线驱动；图源可替换 |
| V. UV 统一依赖 | PASS | 零新增包 |
| VI. 密钥与成本边界 | PASS | MINIMAX_API_KEY 只经 .env/环境变量；按张计费 docstring 标注 |
| VII. 一特性一分支 | PASS | 013-reference-images |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/013-reference-images/
├── plan.md              # 本文件
├── research.md          # Phase 0：base64 直落/命名/修订留痕等 5 项决策
├── data-model.md        # Phase 1：image_generations 表 + 文件布局
├── quickstart.md        # Phase 1：离线验证 + 真机出图
├── contracts/
│   └── images.md        # Phase 1：适配器协议 + 生成入口 + MCP 工具
└── tasks.md             # /skill:speckit-tasks 产出
```

### Source Code (repository root)

```text
orchestrator/
├── images.py            # 新增：ImageProvider 协议 + MinimaxImageProvider +
│                        #   generate_reference_images 入口（原子化）
├── store.py             # 修改：put_image_generation / list_image_generations
├── handoff.py           # 修改：移交包加 images/ 目录
└── mcp_server.py        # 修改：generate_reference_image 工具

db/
└── init_db.py           # 修改：image_generations 幂等 DDL

images/                  # 新增目录（.gitignore 登记）

tests/contract/
├── test_images.py       # 新增：生成/留痕/原子性/宽高比默认/覆盖提示词
├── test_handoff.py      # 修改：带图移交用例
└── test_mcp_server.py   # 修改：generate_reference_image 契约
```

**Structure Decision**: 单项目布局；新逻辑仅 images.py 一个模块。

## 设计要点（Phase 1 摘要）

1. **base64 回包直落盘**（research.md R1）：请求 `response_format="base64"`，
   避开 URL 24h 过期的二次下载；兼容回退仍支持 image_urls 下载。
2. **文件名内容哈希**（R2）：`images/<asset_id>/<sha256[:12]>.png`——同名
   同内容天然去重，不同内容不覆盖（spec Edge Case）。
3. **修订留痕白捡**（R3）：reference_images 变更走 `store.put_asset`（011
   已改造：内容变化自动升版）；生成记录里记变更后版号。
4. **原子性**（R4）：provider 先返回全部字节 → 校验非空 → 写盘 → 最后才
   改资产；任一步失败前序无残留。
5. **宽高比默认**（FR-007）：character/prop → 2:3 竖版，scene/epoch →
   16:9 横版，显式参数优先。

## Constitution Check（Phase 1 复审）

契约先行（I）；胶水层单模块（II）；存储单入口（III）；mock 适配器离线
基线（IV）；零新依赖（V）；密钥环境变量 + 按张计量落库（VI）；分支隔离
（VII）。**全部 PASS。**
