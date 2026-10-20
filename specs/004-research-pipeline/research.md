# Phase 0 Research: 自动资产调研管线

日期：2026-10-20。三个候选组件均基于本地副本源码静态调查
（SearXNGforWindows / gpt-researcher 0.16.0-fork / crawl4ai 0.9.0，证据见各节）。

## R1: 检索层 — 用 SearXNG（本地 Windows 发行版），自写薄客户端

**Decision**: 以 `D:\kimicode_repos\my-gpt-research\SearXNGforWindows` 为检索服务
（仓库外，用户按需启动），适配器内用 httpx 调 `GET {SEARXNG_URL}/search?format=json`。

**关键事实**:
- 启动：仓库根目录跑 `searx/webapp.py`（内置 Python 3.11 embed 或 bat 脚本），
  默认 `127.0.0.1:8888`；**CWD 敏感**（`data/__init__.py` 用 cwd 推目录）
- JSON API 默认已开启（settings.yml `formats: [html, json]`），无需改配置
- 默认仅启用 360search 引擎（其余 200+ 被 disable，反爬原因）；中文查询够用，
  用户可自行加开引擎
- 无 Redis 等额外依赖；`limiter: false` 本地调用不被反爬闸门拦
- 许可证 AGPL-3.0：本项目只作 HTTP 客户端调用、不分发其代码，记录于文档

**Alternatives considered**: 接入 GPT-Researcher 的 searx retriever——见 R2，整个库不引入。

## R2: 编排层 — 自研薄管线，不引入 GPT-Researcher

**Decision**: 不装 gpt-researcher。调研编排（查询 → 检索 → 深抓 → 结构化）在
`orchestrator/research.py` 内自研，结构化复用 002 的 `llm.chat_json()`。

**Rationale**（手册建议仅作参考，用户明确要求不照搬）:
- **角色重叠**：GPT-Researcher 的核心价值是子查询规划 + 报告写作；而本特性
  只需要"调研材料 → 契约资产"，报告环节与我们的 chat_json 抽取重复
- **依赖重量**：`[project].dependencies` 140+ 条（langchain 全家桶、unstructured、
  pymupdf 等），且带 `langchain>=1.0`、`numpy<2.5` 等约束，与现有 uv lock 冲突风险高
- **本地副本是被改过的 fork**（默认模型指向不存在的 `gpt-5.4`，多处本地补丁），
  pin 上游还是 fork 都有维护代价
- **token 成本**：单次 conduct_research ≈ 3-5 次 LLM 调用（含 smart 长上下文）
  + 最多 ~20 页抓取；本特性 1-2 次 chat_json 即可完成结构化

**Alternatives considered**: 装上游 gpt-researcher（RETRIEVER=searx + SEARX_URL）——
上述四条理由否决；若未来需要"深度调研报告"类产物再单独特性评估。

## R3: 深抓层 — Crawl4AI（只用纯抓取 + markdown，跳过其 LLM 抽取）

**Decision**: `uv add crawl4ai`（pin 版本），仅用
`AsyncWebCrawler + DefaultMarkdownGenerator(PruningContentFilter)` 把重点 URL
抓成干净 markdown，结构化交给我们自己的 `llm.chat_json()`。
**不用** `LLMExtractionStrategy`（避免 unclecode-litellm 分叉依赖的配置坑）。

**关键事实**:
- 重依赖：playwright + patchright（强制 install_requires），
  `crawl4ai-setup` 需下载浏览器二进制（150-400MB，一次性）
- Windows 一等支持；入口须先调 `configure_windows_event_loop()`
- 失败不抛异常：`result.success=False` + `error_message`，适配降级策略
- 默认写 `~/.crawl4ai` 缓存；验收用 `CacheMode.BYPASS` 保证干净

**风险与对策**: 安装/浏览器下载可能失败（网络/体积）——
tasks 阶段第一个任务就是安装冒烟 spike；若 spike 失败，降级方案为
trafilatura（轻量纯抓取）替换同一适配器接缝，管线其余部分不变。

**Alternatives considered**: trafilatura/readability（轻，但无 JS 渲染，
中文百科类动态页面抓取质量差）；requests+BeautifulSoup（同缺 JS 渲染）。

## R4: 结构化抽取 — 复用 llm.chat_json() + 契约校验单一入口

**Decision**: 抽取提示词直接以资产契约为目标形态（按 asset_type 给字段指引），
`chat_json`（json_object 模式，002 已验证 DeepSeek 兼容）产出草稿，
 drafts 由 `store.put_asset()` 的 schema 校验把关（原则 III 单一入口）。
JSON 漂移/缺字段 → 重试 1 次 → 仍失败则干净报错，零写入（FR-003）。

**契约事实**（schemas/asset.schema.json）:
- 必填：`asset_id`/`type`/`name`/`provenance`（含 `researched_at`/`retriever`/
  `model`/`confidence` 0-1）
- character 另需 `appearance.visual_prompt` + `persona_spec` 五字段
- 来源 URL 放 `historical_context.sources`（数组）
- `asset_id` 模式 `^(char|prop|scene|epoch)_[a-z0-9_]+$`

## R5: 语义去重 — 共享嵌入助手抽到 orchestrator/embedding.py

**Decision**: 把 003 的 `_embedding_config` / `_build_embedding_model`（及常量）
从 `persona_tinytroupe.py` 提升到新模块 `orchestrator/embedding.py`，
persona 适配器改为 import（003 行为不变，回归套件兜底）。
去重算法：
- 文本 = `name + appearance.description/visual_prompt`，同一 type 内比较
- 余弦 ≥ `RESEARCH_DEDUP_THRESHOLD`（默认 0.85，探针后可调）→ 判重，
  返回已有 asset_id，不写入
- 嵌入服务不可用（配置缺失/预检失败/调用异常）→ 降级为 name 精确匹配 + 降级日志
  （FR-005，与 003 降级语义一致）
- store.py 增加只读方法 `list_assets(type)`（原则 III：store 仍是唯一入口，
  只是入口多一个读方法）；资产量级小，现算向量即可，不做嵌入缓存

**Alternatives considered**: 手册的"SQLite + embedding 缓存"——资产量为个位数到
几十，现算成本可忽略，缓存是过度设计。

## R6: 环境变量清单（FR-007，原则 VI）

| 变量 | 含义 | 默认 |
|---|---|---|
| `SEARXNG_URL` | SearXNG 服务根地址 | 无（未设=明确报错，FR-007） |
| `RESEARCH_MAX_URLS` | 单次调研深抓的 URL 上限 | `5` |
| `RESEARCH_TIMEOUT_S` | 单页抓取/检索超时 | `30` |
| `RESEARCH_DEDUP_THRESHOLD` | 语义去重余弦阈值 | `0.85` |

复用：`EMBEDDING_*`（003）、`DEEPSEEK_*`/`OPENAI_*`（002）。键位进 `.env.example`；
SearXNG 服务与 crawl4ai 浏览器二进制在仓库外。

## R7: 模块布局与入口（原则 II/IV）

- `orchestrator/research.py`：调研管线 + SearXNG 薄客户端 + Crawl4AI 封装
  —— 外部调研栈的全部接触面集中于此一个适配器模块
- `orchestrator/embedding.py`：R5 的共享嵌入助手（003 代码搬家）
- `scripts/research_asset.py`：CLI 入口（`--query --type --db`），打印 asset_id 或错误
- 离线测试：searxng HTTP / crawler / llm 三层 mock，Mock 基线不依赖任何外部进程
- `store.py`：仅加 `list_assets(type)` 读方法

## R8: asset_id 生成与溯源填充

- `asset_id` = `{prefix}_{sha1(name)[:10]}`（prefix 按 type 映射 char/prop/scene/epoch）：
  中文名无法可靠 slug 化，hash 确定性可重入（同名重复调研天然命中同一 id）
- `provenance.retriever = "searxng+crawl4ai"`（与手册验收口径一致）；
  `model` = 实际抽取用模型名；`researched_at` = ISO8601；
  `confidence` = 来源数启发式 `min(0.5 + 0.1×sources, 0.9)`
- `historical_context.sources` = 实际抓取成功的 URL 列表（非空才入库，FR-002）

## R9: 依赖与回归面

- 新增依赖仅 `crawl4ai`（uv add + pin，原则 V）；SearXNG 服务零 Python 依赖（HTTP）
- 003 代码搬家（R5）是唯一触碰既有特性的改动，由 46 项离线回归兜底
- M1/M2/003 不回归；调研管线与仿真链路无共享运行时状态（FR-006）
