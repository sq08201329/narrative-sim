# Phase 0 Research: TinyTroupe 真后端接入（M2）

调研对象：本地源码副本 `D:/kimicode_repos/projects/my_mas/TinyTroupe`
（commit `a6244b358a1fe1c71bf751f7ba0f8dfa368ec5a4`，v0.7.0）。
以下每条结论都有源码行号证据，行号以该 commit 为准。

## D1: 依赖声明 —— git URL + commit pin

- **Decision**: `uv add "tinytroupe @ git+https://github.com/microsoft/TinyTroupe.git@a6244b358a1fe1c71bf751f7ba0f8dfa368ec5a4"`。
- **Rationale**: 宪章原则 IV/V 要求 pin commit 且禁 PyPI 占位包；本地副本已核实
  该 commit 即 v0.7.0（`pyproject.toml:11`）。
- **Alternatives**: PyPI `tinytroupe` 是占位包（手册已警示）；本地 path 依赖不可复现
  （换机器即失效）；Gitee 镜像仅在 GitHub 不通时作为安装备选，不入 pyproject。

## D2: 角色构建 —— `include_persona_definitions`

- **Decision**: `TinyPerson(name=<asset_id>)` + `include_persona_definitions(persona_dict)`；
  `persona_spec.speech_style` 映射为 `style` 键。
- **Rationale**: prompt 模板强制要求 persona 含 `style` 字段
  （`tinytroupe/agent/prompts/tiny_person.v2.mustache:49-50`）；批量合并接口为
  `tiny_person.py:497-510`。实例名用 `asset_id`：全局注册表 `TinyPerson.all_agents`
  重名即抛 `ValueError`（`tiny_person.py:280-295`），asset_id 天然唯一。
- **Alternatives**: `load_specification(dict)`（`tiny_person.py:2178-2223`）走完整
  反序列化，对纯 persona 字典过重，拒绝。

## D3: 状态投喂与动作读取

- **Decision**: 每回合用 `listen(text)` 投喂可见状态摘要（场景、回合数、上回合事件），
  然后 `act(return_actions=True)` 取动作；映射 `TALK→dialogue`、`THINK→inner_voice`、
  `DONE→丢弃`；`emotion` 取 `cognitive_state.emotions`。
- **Rationale**: `act()` 默认返回 None，`return_actions=True` 返回
  `list[{"action": {...}, "cognitive_state": {...}}]`（`tiny_person.py:746-751, 909-910`）；
  动作类型枚举在 prompt 而非代码（`tiny_person.v2.mustache:48-54`），0.7.0 只有
  TALK/THINK/DONE；`listen()` 纯文本零额外开销（`tiny_person.py:912-940`）。
- **Alternatives**: `pop_latest_actions()`（`tiny_person.py:1800-1809`）需经缓冲区，
  不如 return_actions 直接；TinyWorld 对单角色属过度（`environment=None` 完全可行，
  `tiny_person.py:1406-1412`），拒绝。

## D4: 实例缓存 —— dict[asset_id, TinyPerson]

- **Decision**: 后端内部维护 `dict`，键 `asset_id`；仿真生命周期内复用。
- **Rationale**: 跨回合记忆连续 = episodic memory 留在实例上（`_observe` 写入，
  `tiny_person.py:1180-1223`）；同时规避全局注册表重名报错。
- **Alternatives**: 每回合重建（手册明令禁止，记忆断裂）。

## D5: 质量校验与终极失败处理

- **Decision**: `config.ini` 设 `[ActionGenerator] enable_quality_checks=True`、
  `continue_on_failure=True`；适配器对 `act()` 的终极异常（API 全失败时
  `send_message` 返回 None → TypeError 向上传播）再做一层捕获重试（最多 3 次），
  仍失败则抛明确错误，**该回合事件不写库**。
- **Rationale**: 包内默认 `enable_quality_checks=False`（`tinytroupe/config.ini:87`），
  必须显式开启；开启后失败路径是"返回分数最高候选"（`action_generator.py:295-299`），
  不抛异常；结构层另有 `@repeat_on_error(retries=5)`（`tiny_person.py:775`）兜底，
  终极失败会穿透到调用方（`openai_client.py:400-401` → TypeError）。
- **Alternatives**: `continue_on_failure=False` 抛 `PoorQualityActionException`
  （`action_generator.py:301-302`）过于刚硬，单回合失败即终止仿真，拒绝。

## D6: DeepSeek 接入 —— 环境变量 OPENAI_BASE_URL（关键事实）

- **Decision**: `.env` 提供 `OPENAI_API_KEY` 与 `OPENAI_BASE_URL=https://api.deepseek.com`；
  `config.ini` 设 `[OpenAI] api_type=openai`、`model=deepseek-flash`。
  适配器在 import tinytroupe 之前校验这两个环境变量存在，缺失即报明确错误。
- **Rationale**: TinyTroupe 的 `OpenAIClient` 构造 `OpenAI()` 时**不传 base_url**
  （`clients/openai_client.py:172-174`），config.ini 的 `BASE_URL` 键只有 OllamaClient
  消费（`clients/ollama_client.py:23-24`）；全源码无 `OPENAI_BASE_URL` 字样 —— 但
  openai SDK 自身读该环境变量，这是唯一不改源码的接入路径。
- **Alternatives**: 继承 `OpenAIClient` 重写 `_setup_from_config` 传 base_url 再
  `register_client`（`clients/__init__.py:49-57, 118`）—— 能work但侵入第三方内部，
  升级即碎，拒绝；设 `OPENAI_API_BASE`（旧变量名）openai SDK 新版本不再读，拒绝。

## D7: 成本记账 —— client 单例统计 + store 落库

- **Decision**: 运行开始 `client().reset_cost_stats()`，结束 `get_cost_stats()` 取
  `total_tokens`，经新增的 `store.update_run_cost(run_id, tokens)` 写入
  `runs.token_cost`；仿真串行执行。
- **Rationale**: 统计只在 client 单例上（`clients/openai_client.py:672-723`），
  无 run 维度隔离 —— 串行 + 运行前后 reset/读取即可正确归属；`runs.token_cost`
  列已存在（001 建表）。
- **Alternatives**: 并发多 run —— 统计互相污染，本特性明确串行，M4 再议。

## D8: Embedding 地雷规避

- **Decision**: 角色只用默认 faculties，绝不挂 grounding；适配器在 import
  tinytroupe 前先确认 `OPENAI_API_KEY` 存在。
- **Rationale**: `import tinytroupe` 时即实例化 `OpenAIEmbedding`
  （`__init__.py:442-445`），llama-index 构造期缺 key 可能直接炸；
  DeepSeek 无 embeddings API，走 `VectorStoreIndex` 的路径（`agent/grounding.py:92`）
  必 4xx。纯 TinyPerson 行动流不调 embedding，不碰即可。
- **Alternatives**: 自配 embedding 模型 —— 超出 M2 范围，拒绝。

> **实测补记（2026-10-19，实施期修正）**：D8 的"不接 grounding 就碰不到 embedding"
> 被证伪 —— `SemanticMemory._store`（`agent/memory.py:609`）与
> `retrieve_relevant_for_current_context`（`agent/tiny_person.py:1433`）在普通
> `act()` 流程中同样调用 embedding，且 llama-index 默认打 api.openai.com、
> 每次 10 轮超时重试。最终方案：`_LocalSemanticMemory` 降级为本地列表
  （跳过向量连接器），episodic 记忆不受影响。恢复路径候选：本地嵌入模型
  （如 sentence-transformers 格式的 EmbeddingGemma 2，替换 llama-index 的全局
  `Settings.embed_model`），单独立项。

## D9: 测试策略 —— 离线单元测试 + 打标在线验收

- **Decision**: `tests/contract/test_tinytroupe_backend.py` 用 monkeypatch 替换
  TinyPerson/act 与 cost stats（离线、进回归套件）；`tests/integration/test_real_chain.py`
  打 `@pytest.mark.real`，无 `OPENAI_API_KEY` 时 `pytest.skip`。
- **Rationale**: 宪章原则 IV 要求 M1 离线基线永不回归 —— 回归套件必须全程离线；
  真后端验收依赖外部服务，必须可隔离。
- **Alternatives**: 真后端验收进默认套件 —— 无密钥环境必红，拒绝。

## D10: cwd 守卫

- **Decision**: `run_real_chain.py` 启动时校验 `Path.cwd() == 项目根`，否则报明确
  错误退出非 0。
- **Rationale**: TinyTroupe 读 `Path.cwd()/config.ini`（`utils/config.py:128`），
  读不到时**静默**用包内默认（`model=gpt-5-mini`，`tinytroupe/config.ini:19`）——
  手册 4.2 已警示此坑；静默错配比直接报错贵得多。
- **Alternatives**: 信任文档说明 —— 已证明是高频坑，拒绝。
