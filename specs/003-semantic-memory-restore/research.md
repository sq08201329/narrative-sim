# Phase 0 Research: 恢复语义记忆（本地嵌入服务接入）

日期：2026-10-19。所有结论均已实测（嵌入服务在线，`scripts/probe_embedding_service.py`）。

## R1: llama-index OpenAIEmbedding 能否指向自定义端点

**Decision**: 能用，但必须用 `model_name=` kwarg，不能用 `model=` 形参。

**实测证据**:
- `OpenAIEmbedding(model="eg2-text-270m.litertlm", ...)` →
  `ValueError: 'eg2-text-270m.litertlm' is not a valid OpenAIEmbeddingModelType`
  （`model=` 过枚举白名单，`embeddings/openai/base.py:315`）
- `OpenAIEmbedding(model_name="eg2-text-270m.litertlm", api_base="http://127.0.0.1:9379/v1",
  api_key="dummy")` → 正常，`get_text_embedding` 返回 768 维向量；
  客户端结果与裸 POST `/v1/embeddings` 余弦 = 1.000000（客户端无隐藏变换）
- 原理：`model_name` kwarg 在 `base.py:318-320` 直接覆盖 `_query_engine/_text_engine`，
  跳过 `get_engine` 白名单（白名单仍会对默认 `model` 形参求值，但不传即合法）

**Alternatives considered**: 适配器内自写薄嵌入客户端（只 POST /v1/embeddings）——
保留为后备方案，因 OpenAIEmbedding 实测可用而不需要。

## R2: litert-lm 服务端是否自动添加 EmbeddingGemma 2 任务前缀

**Decision**: 不加。适配器侧子类化 OpenAIEmbedding，在文档/查询两个方向分别补前缀：
`task: search result | text: `（文档，对应 `_get_text_embedding(s)`）、
`task: search query | text: `（查询，对应 `_get_query_embedding`）。

**实测证据**:
- 裸文本向量 vs 手工加前缀文本向量：余弦 = 0.8707 ≠ 1.0 → 服务端未自动加前缀
- 检索区分度（query 前缀 + doc 前缀）：相关 0.7836 / 无关 0.6613（间隔 0.12），
  语义检索有效；参考 LiteRT-LM issue #3929（任务提示需客户端添加）

**Alternatives considered**: 不加前缀直接裸嵌——可用但违背模型卡推荐用法，检索质量打折。

## R3: TinyTroupe 语义记忆的嵌入通道与恢复点

**Decision**: 002 的降级是 `LocalSemanticMemory`（`_store` 只进本地列表、`retrieve_relevant`
恒返回 `[]`）。恢复方式 = 不再注入降级实例，让 TinyPerson 用默认 `SemanticMemory`
（其 `_store` 会把 engram 建成 llama-index Document 交给
`BaseSemanticGroundingConnector` → `VectorStoreIndex` → `Settings.embed_model`），
并在 import tinytroupe 之后、首个 TinyPerson 创建之前，把 `Settings.embed_model`
覆盖为我们的子类实例。

**关键事实**:
- `tinytroupe/__init__.py:442-445` 在 import 时实例化默认 `OpenAIEmbedding`
  （走 `OPENAI_API_BASE` env → 会指向 DeepSeek，错的目标）。该实例只有被用到才发请求，
  因此 import 不炸，但我们 MUST 在使用前覆盖 `Settings.embed_model`。
- `SemanticMemory._store` 内部已 try/except「Ignoring and continuing」（memory.py:608），
  单条写入失败不崩溃；但 `retrieve_relevant` 无保护 → 见 R4。
- `TinyPerson.__init__` 接受 `semantic_memory=` 注入（tiny_person.py），
  降级路径继续复用该接缝。

**Alternatives considered**: 改 TinyTroupe config.ini 的 `embedding_model` 指向本地服务——
config.ini 读 `Path.cwd()`，且无法表达 api_base/前缀/超时，放弃。

## R4: 失败与超时的拦截边界（FR-005、US2-AC2）

**Decision**: 嵌入子类对 `_get_query_embedding` / `_get_text_embedding(s)` 做全异常拦截：
- 预检失败或服务中途宕机 → 返回 768 维零向量并记录降级日志（只打一次，不刷屏）
- 超时上限 `EMBEDDING_TIMEOUT_S`（默认 10s，OpenAIEmbedding `timeout` 形参原生支持），
  `max_retries=1`（默认 10 次指数退避会把单次失败拖成分钟级，违反 SC-003）
- 空文本/纯空白：不发请求，直接返回零向量（spec Edge Case）
- 超长文本：按 `EMBEDDING_MAX_CHARS`（默认 2000 字符）截断后嵌入

零向量的效果：写入正常落索引、召回退化为近似随机排序——仿真不崩、行为可解释，
与 002「忽略并继续」的精神一致。

## R5: 预检与降级判定（FR-002）

**Decision**: 后端构造时（`person_cls is None` 的真后端路径）：
- 未设 `EMBEDDING_API_BASE` → 直接走 002 降级路径（LocalSemanticMemory），
  输出降级提示（US3-AC1 选定的口径：降级，不报错）
- 已设 → 预检：`GET {base}/models`（超时 5s），返回列表中含 `EMBEDDING_MODEL`
  且一次最小 embeddings 调用成功 → 真实语义模式；任一失败 → 降级路径 + 提示
- 降级提示经后端只读属性暴露（如 `semantic_mode: "real" | "degraded: <原因>"`），
  由 `run_real_chain.py` 打印；适配器内部用 logging

## R6: 环境变量清单（FR-003，宪章原则 VI）

| 变量 | 含义 | 默认 |
|---|---|---|
| `EMBEDDING_API_BASE` | 嵌入服务 OpenAI 兼容根地址 | 无（未设=降级） |
| `EMBEDDING_MODEL` | 模型标识（预检匹配 + 请求 model 字段） | `eg2-text-270m.litertlm` |
| `EMBEDDING_TIMEOUT_S` | 单次嵌入调用超时秒数 | `10` |
| `EMBEDDING_MAX_CHARS` | 超长文本截断字符数 | `2000` |

键位进 `.env.example`；仓库代码、脚本、文档不出现具体地址字面量
（文档中以 `<嵌入服务地址>` 占位）。litert-lm 本体与启动脚本在仓库外（FR-007）。

## R7: 依赖与回归面

- 无新增依赖：`llama-index-embeddings-openai`、`httpx` 已随 TinyTroupe 装入（原则 V）
- 嵌入接入代码全部在 `orchestrator/persona_tinytroupe.py`（原则 II、FR-008）
- M1/M2 不回归：MockBackend 与注入 `person_cls` 的离线测试路径不触碰嵌入逻辑（FR-006）
- `scripts/probe_embedding_service.py` 保留为 US1-AC2 的召回探针（不调 LLM 即可验证
  语义存取），实施期扩展为「写入—若干干扰—召回」的完整验收形态
