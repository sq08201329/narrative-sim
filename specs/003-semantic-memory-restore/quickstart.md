# Quickstart: 恢复语义记忆（本地嵌入服务接入）

验证本特性的三种形态：真实嵌入、优雅降级、离线回归。
前置：002 环境已就绪（uv sync 完成、`DEEPSEEK_API_KEY` 在环境变量中）。

## 0. 启动嵌入服务（仓库外）

```powershell
pwsh D:\gh_projects\embeddinggemma-2\start-embedding-api.ps1
```

服务就绪后监听本地端口（OpenAI 兼容 `/v1/embeddings`）。该服务由用户按需启动，
本项目不管理其生命周期；具体地址以你本机启动脚本输出为准，写入环境变量
`EMBEDDING_API_BASE`（如 `.env`，键位见 `.env.example`）。

## 1. 召回探针（US1-AC2，不调 LLM）

```bash
uv run python scripts/probe_embedding_service.py
```

预期：退出码 0；输出显示向量维度 768；写入的「相关文档」在若干干扰文档之后，
经查询前缀检索的余弦相似度高于「无关文档」——证明语义存与取均经嵌入服务完成。

## 2. 真链路 + 真实语义模式（US1-AC1）

```bash
uv run python scripts/run_real_chain.py
```

预期：输出含「语义检索：真实嵌入服务」（或等价的 semantic_mode=real 提示）；
≥5 事件落库、契约校验全过、验收通过（沿用 002 判定）。

## 3. 真链路 + 服务离线降级（US2-AC1）

停掉嵌入服务（或直接 unset `EMBEDDING_API_BASE`），再跑：

```bash
uv run python scripts/run_real_chain.py
```

预期：退出码 0、验收通过；输出含明确降级提示（semantic_mode=degraded 及原因），
行为与 002 一致。

## 4. 离线回归（SC-004）

```bash
uv run pytest -m "not real"
```

预期：全部通过（001/002 既有测试 + 003 新增离线单测：预检判定、降级回退、
前缀/空文本/截断/超时拦截，均 mock 在 httpx 层，不需要真实服务）。
