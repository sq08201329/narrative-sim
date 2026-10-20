# Implementation Plan: 自动资产调研管线

**Branch**: `004-research-pipeline` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-research-pipeline/spec.md`

## Summary

实现"查询词 → 契约资产入库"的自动调研管线：SearXNG（本地 Windows 发行版，HTTP 检索）
→ Crawl4AI（重点 URL 深抓为干净 markdown，跳过其 LLM 抽取）→ 复用 002 `llm.chat_json()`
按资产契约结构化 → `store.put_asset()` 校验入库；入库前用语义嵌入去重
（003 嵌入助手提升到 `orchestrator/embedding.py` 共享，降级为名称精确匹配）。
不引入 GPT-Researcher（理由见 [research.md](research.md) R2）。外部调研栈接触面
全部集中在 `orchestrator/research.py` 一个适配器模块。

## Technical Context

**Language/Version**: Python 3.12（uv 管理）
**Primary Dependencies**: 新增 crawl4ai（pin，含 playwright/patchright 浏览器）；
httpx / llm.py / store.py / embedding.py 复用既有
**Storage**: SQLite（store.py 仅加 `list_assets(type)` 读方法）
**Testing**: pytest 离线套件（searxng HTTP / crawler / llm 三层 mock）
+ 真机验收脚本（需 SearXNG 服务 + DeepSeek 密钥）
**Target Platform**: Windows 本机开发环境
**Performance Goals**: 服务不可达时 60s 内明确报错（SC-003）；
单次调研深抓 ≤ `RESEARCH_MAX_URLS`（默认 5）页
**Constraints**: 调研接触面 100% 在 research.py；服务地址零硬编码；
失败零部分写入；M1/M2/003 不回归
**Scale/Scope**: 新增 2 个模块 + 1 个 CLI 脚本 + 1 个测试文件；
003 嵌入助手代码搬家（行为不变）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 说明 |
|---|---|---|
| I 契约先行 | ✅ | FR-009：不动资产/事件契约；put_asset schema 校验把关 |
| II 单一胶水层 | ✅ | 调研栈接触面集中在 `orchestrator/research.py`；嵌入复用统一经 `embedding.py` |
| III 存储单一入口 | ✅ | 写入只走 `store.put_asset()`；仅新增只读 `list_assets(type)` |
| IV 适配器隔离 + Mock 基线 | ✅ | 离线测试三层 mock，不依赖任何外部进程 |
| V UV 依赖管理 | ✅ | 仅 `uv add crawl4ai`（pin）；SearXNG 为外部 HTTP 服务零依赖 |
| VI 密钥与成本边界 | ✅ | SEARXNG_URL 等走环境变量；服务/浏览器二进制在仓库外 |
| VII 一特性一分支 | ✅ | 当前分支 `004-research-pipeline` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/004-research-pipeline/
├── plan.md              # 本文件
├── research.md          # Phase 0：9 项决策（含 GPT-Researcher 否决理由）
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── tasks.md             # Phase 2（/skill:speckit-tasks 产出）
```

### Source Code (repository root)

```text
orchestrator/
├── research.py           # 新增：调研管线 + SearXNG 薄客户端 + Crawl4AI 封装
├── embedding.py          # 新增：003 嵌入助手共享化（_embedding_config /
                          #   _build_embedding_model / 常量，自 persona_tinytroupe 搬入）
├── persona_tinytroupe.py # 改为 import embedding.py（行为不变）
├── store.py              # 仅加 list_assets(type) 读方法
└── llm.py                # 不改（chat_json 复用）

scripts/
└── research_asset.py     # 新增 CLI：--query --type --db，打印 asset_id / 明确错误

tests/contract/
└── test_research_pipeline.py  # 新增：三层 mock 的离线测试

.env.example              # 加 SEARXNG_URL / RESEARCH_MAX_URLS / RESEARCH_TIMEOUT_S /
                          # RESEARCH_DEDUP_THRESHOLD 键位
```

**Structure Decision**: 单项目布局沿用 001-003 既有结构；调研栈适配器独立成模块
（原则 II），嵌入助手共享化是唯一的跨特性触碰（R5，回归套件兜底）。

## Complexity Tracking

无（Constitution Check 全过）。

## 风险备忘

- **crawl4ai 安装/浏览器下载失败**（重依赖 + CDN 下载）：tasks 首个任务为安装冒烟
  spike；失败则按 research.md R3 降级为 trafilatura 替换同一接缝
- **360search 单引擎覆盖不足**：真机验收若检索质量差，用户在 SearXNG settings.yml
  加开引擎即可，不动本仓库代码
