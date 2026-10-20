# Data Model: 恢复语义记忆（本地嵌入服务接入）

本特性不引入持久化实体，不改两张契约（FR-006），不触碰 store.py。
以下为运行时概念模型。

## 嵌入服务描述（EmbeddingServiceConfig）

来源：环境变量（见 research.md R6），进程内存，无持久化。

| 字段 | 类型 | 来源 | 校验规则 |
|---|---|---|---|
| api_base | str | `EMBEDDING_API_BASE` | 未设 → 直接降级，不构造嵌入客户端 |
| model | str | `EMBEDDING_MODEL` | 默认 `eg2-text-270m.litertlm`；预检时必须出现在 `GET {base}/models` 返回中，否则降级 |
| timeout_s | float | `EMBEDDING_TIMEOUT_S` | 默认 10；单次嵌入调用上限，超时按失败处理 |
| max_chars | int | `EMBEDDING_MAX_CHARS` | 默认 2000；超出截断 |

## 语义模式（SemanticMode）

后端只读属性，供真链路脚本打印降级提示：

- `real`：预检通过，语义记忆写入/召回均经嵌入服务向量化
- `degraded: <原因>`：未配置 / 服务不可达 / 模型不匹配 / 预检调用失败 →
  注入 002 的 LocalSemanticMemory（只存不检）

## 语义记忆条目（TinyTroupe 内部，本特性不改形态）

engram dict（`role/content/type/simulation_timestamp`）→ llama-index `Document`
（JSON 文本）→ `VectorStoreIndex`（`Settings.embed_model` 向量化）。
失败语义（research.md R4）：嵌入调用异常/超时/空文本 → 768 维零向量，
写入照落、召回退化为近似随机排序，仿真不崩溃。

## 向量维度

固定 768（eg2-text-270m 实测）；零向量回退与该维度一致，
不进入任何持久化，无跨运行兼容性问题。
