# Contract: DM 裁决提供者（orchestrator/dm.py）

**Feature**: 010-dm-adjudicator | **Date**: 2026-10-21

本契约先行于实现（宪章 I）。所有签名为对外承诺，实现与测试以此为准。

## 1. 工厂函数

```python
def build_dm_provider(options: "DMOptions") -> "DMProvider":
    """构造真实裁决者（LiteLLMDMProvider 实例）。

    环境桥接（002 模式）：仅有 DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL 时
    映射到 OPENAI_API_KEY/OPENAI_BASE_URL；两者都缺时抛
    DMConfigError("缺少环境变量 ...")，消息指明需配置的键名。

    模型串：f"openai/{options.model}"。
    返回对象满足 worldseed DMProvider 协议（async judge(ctx)）。
    """
```

- **异常**: `DMConfigError(RuntimeError)` —— 密钥/配置缺失时抛出，消息含缺失键名。
- **副作用边界**: 仅设置进程环境变量桥接（不存在的才补，不覆盖已有 OPENAI_*）；
  不发起网络调用（litellm client 惰性初始化）。

## 2. 史料注入

```python
def build_dm_knowledge(store: Store, asset_ids: list[str],
                       budget: int = 2000) -> str:
    """汇总各资产调研原料为 dm_knowledge 文本。

    每条原料渲染为 "【{query}】{context 截断}"，逐条累加；
    加上整条会超预算时停止（尾部整条丢弃）。无原料返回 ""。
    永不抛异常（单资产缺料跳过）。
    """
```

## 3. 世界循环开关（orchestrator/world.py 变更）

```python
def build_scene_config(store, character_ids, location_id,
                       dm: DMOptions | None = None) -> dict:
    """dm is None 时输出与 006 版本逐字节一致（向后兼容锚点）。
    dm 非 None 时：actions.act.dm 挂裁决配置；scene.dm_knowledge
    注入史料；scene.max_dm_calls 设成本帽。"""

def run_world(store, run_id, world_id, character_ids, location_id, ticks,
              backend, resume=False, dm: DMOptions | None = None) -> list[dict]:
    """dm 非 None 时构造 provider 传入引擎；run 结束后 dm_call 审计落库。"""
```

## 4. 存储契约（orchestrator/store.py 变更）

```python
def put_dm_call(self, run_id: str, tick: int, action: str, agent_id: str,
                params: str, hint: str, narrative: str, effects: str,
                tokens_in: int, tokens_out: int, elapsed_s: float,
                failed: bool) -> int: ...

def list_dm_calls(self, run_id: str) -> list[dict]: ...
    # 按 id 升序；字段与 data-model.md 的 dm_calls 表一一对应
```

## 5. CLI 契约（scripts/run_world_chain.py 变更）

| 参数 | 默认 | 语义 |
|------|------|------|
| `--dm` | 关 | 启用真实裁决（缺密钥时退出码非零、消息指明缺哪个键） |
| `--dm-knowledge-chars N` | 2000 | 史料注入预算 |
| `--dm-max-calls N` | 50 | 裁决成本帽 |

不带 `--dm` 的既有命令行行为与输出保持不变。

## 6. 测试契约

- 离线测试（`tests/contract/test_dm_adjudicator.py`）零外部调用：引擎层以
  worldseed `MockDMProvider` 驱动，验证 act 裁决配置注入、效果落世界状态、
  dm_calls 审计行、失败降级路径、dm=None 兼容锚点。
- 真机验收标 `@pytest.mark.real`，不进默认测试集。
