# Contract: 真后端（TinyTroupe）适配协议

## 接口（不变）

`TinyTroupeBackend` 实现既有 `PersonaBackend` Protocol：

```python
def act(persona_spec: dict, visible_state: dict) -> dict:
    # 返回 {"kind": "dialogue|inner_voice|action", "content": str, "emotion": str}
```

## 映射表

详见 [../data-model.md](../data-model.md) 的 persona_spec 映射与动作映射两表。
要点：`speech_style → style`；`TALK→dialogue`、`THINK→inner_voice`、`DONE→丢弃`；
`emotion ← cognitive_state.emotions`。

## 错误契约

| 场景 | 行为 |
|------|------|
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` 缺失 | 抛指明变量名的明确错误（import tinytroupe 之前拦截） |
| cwd 非项目根 | 链路脚本拒绝启动，退出码非 0 |
| 动作解析重试（3 次）耗尽 | 抛明确错误，该回合事件不写库，run 标记 failed |
| persona_spec 缺契约必填键 | 资产入库阶段已被契约校验拦截（001 既有） |

## 调用时序

```
construct(asset_id, persona_spec)  →  缓存实例（首次）
listen(visible_state 摘要)          →  每回合投喂
act(return_actions=True)           →  取动作 + cognitive_state
映射为协议返回                      →  TALK/THINK/DONE 处理
```

成本：运行开始 `reset_cost_stats()`，结束 `get_cost_stats()["total_tokens"]`
→ `store.update_run_cost()`。仿真串行，禁止并发 run（统计单例无隔离）。
