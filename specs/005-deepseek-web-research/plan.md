# Implementation Plan: GPT-Researcher 接入 DeepSeek 检索腿（B 方案）

**Branch**: `005-deepseek-web-research` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-deepseek-web-research/spec.md`

## Summary

在本仓库新建 GPT-Researcher retriever 插件包 `plugins/gptr-deepseek-retriever/`
（entry-point 组 `gpt_researcher.retrievers` 注册 `deepseek`，fork 零改动），
把 DeepSeek 官方 Search API 接成 gptr-mcp 的检索腿：`content` 全文直通
`raw_content`（`requires_scraping=False`，省掉 GPT-R 抓取轮）、摘要垫底、
高排序缺口条目 Fetch 补抓（≤2 次）；插件全程不抛异常（429 退避、401/402 警告、
空结果收尾）。服务端仅改 `RETRIEVER=deepseek` 环境变量并安装插件；
004 管线仅溯源标签改为环境变量驱动（默认 `gptr-mcp(deepseek-search)`）。
技术细节与机制证据见 [research.md](research.md)。

## Technical Context

**Language/Version**: Python 3.12（uv 管理主项目；插件运行于 gptr-mcp venv 3.12）
**Primary Dependencies**: 插件仅依赖 httpx（主 lock 已有；entry-point 机制
由 gpt-researcher fork 提供，零 fork 改动）
**Storage**: SQLite（不动）
**Testing**: pytest 离线套件（插件类直接 import + HTTP 层 mock）
+ 真机验收（gptr-mcp 换腿，SearXNG 停开）
**Target Platform**: Windows 本机开发环境
**Performance Goals**: 单次调研 ≈ 5 次 Search + ≤2 次 Fetch（≈0.03 元）；
429 退避 2s/4s ≤2 次
**Constraints**: 插件 100% 在仓库内、fork 零改动；插件任何路径不抛异常；
004 管线行为兼容；M1-M4 不回归
**Scale/Scope**: 1 个插件包（~120 行）+ 1 个测试文件 + research.py 一处
标签改动 + .env.example / quickstart 文档

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 判定 | 说明 |
|---|---|---|
| I 契约先行 | ✅ | FR-008：不动两张契约；retriever 标签为自由文本字段 |
| II 单一胶水层 | ✅ | DeepSeek 检索接触面集中在插件包（GPT-R 侧）；004 调研适配器不变 |
| III 存储单一入口 | ✅ | 写入仍只走 `store.put_asset()` |
| IV 适配器隔离 + Mock 基线 | ✅ | 插件离线测试 mock HTTP 层，零真实 API 依赖 |
| V UV 依赖管理 | ✅ | 插件为仓库内 pip 包（pyproject），主 lock 仅加 httpx 既有项 |
| VI 密钥与成本边界 | ✅ | 密钥复用 DEEPSEEK_API_KEY；端点 env 可覆盖；补抓闸门 |
| VII 一特性一分支 | ✅ | 当前分支 `005-deepseek-web-research` |

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/005-deepseek-web-research/
├── plan.md              # 本文件
├── research.md          # Phase 0：8 项决策（fork 机制证据 + API 事实）
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
└── tasks.md             # Phase 2（/skill:speckit-tasks 产出）
```

### Source Code (repository root)

```text
plugins/gptr-deepseek-retriever/
├── pyproject.toml             # entry-point: gpt_researcher.retrievers → deepseek
└── gptr_deepseek_retriever/
    ├── __init__.py            # 导出 DeepSeekSearchRetriever
    └── deepseek.py            # retriever 类（Search/Fetch/容错/补抓闸门）

orchestrator/
└── research.py                # 一处改动：provenance.retriever 读
                               # GPTR_MCP_RETRIEVER_LABEL，默认 gptr-mcp(deepseek-search)

tests/contract/
└── test_gptr_deepseek_retriever.py  # 新增：插件离线测试（HTTP mock）

.env.example                   # 加 GPTR_MCP_RETRIEVER_LABEL；插件侧变量在
                               # quickstart 文档化（服务端 venv 读取）
```

**Structure Decision**: 插件以独立 pip 小包放 `plugins/`（entry-point 要求
可安装元数据）；它与 orchestrator 无 import 关系，运行时是 gptr-mcp venv 的
一部分——这是本仓库代码进入 GPT-R 进程的唯一通道，形态干净。

## Complexity Tracking

无（Constitution Check 全过）。

## 风险备忘

- **插件加载路径**：entry-point 需 gptr-mcp venv 重装后才可见（pip 元数据），
  tasks 含安装验证 spike（`RETRIEVER=deepseek` 启动 + list 通过）
- **content 是否真全文**：官方文档表述为"网页正文"，若实测是摘要级，
  raw_content 直通仍成立（GPT-R 上下文压缩兜底），无需改设计
- **fork 升级**：鸭子类型契约无基类约束，fork 大版本升级时需复核
  `actions/retriever.py` 插件加载路径（research.md R1 已存证行号）
