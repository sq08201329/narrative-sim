# Contract: 幕间记忆（orchestrator/interlude.py + MCP）

**Feature**: 012-interlude-memory | **Date**: 2026-10-21

本契约先行于实现（宪章 I）。

## 1. 核心业务函数

```python
# orchestrator/interlude.py

class InterludeError(RuntimeError): ...   # 来源 run 不存在/无事件等

def visible_to_character(event: dict, asset_id: str,
                         world_characters: list[str]) -> bool:
    """三规则过滤（data-model.md）：inner_voice 仅本人 /
    visible_to 列内 / 其余公开。"""

def generate_memories(store: Store, run_id: str,
                      character_ids: list[str],
                      channel: str = "template",
                      regenerate: bool = False) -> list[dict]:
    """为角色集生成（或复用）幕间记忆。

    - 来源 run 不存在 → InterludeError；无事件 → 每角色空摘要落库
      （summary=""，event_refs=[]，显式空语义）
    - 同键已存在且 regenerate=False → 直接返回库存行（tokens 为 0，
      reused=True 标注）
    - regenerate=True → 追加新 revision
    - channel: "template"（确定性）| "llm"（chat 接缝，token 落库）
    - 返回 [{asset_id, revision, summary, event_refs, channel, reused}]
    """

def get_memories(store: Store, run_id: str,
                 asset_id: str | None = None) -> list[dict]:
    """读取当前版记忆；asset_id 缺省取该 run 全部。无记录返回 []。"""
```

## 2. 注入接缝

```python
# orchestrator/persona.py —— PersonaBackend 协议新增
def seed_memory(self, asset_id: str, text: str) -> None:
    """注入上一幕记忆。MockPersonaBackend 记录到 self.seeded:
    list[tuple[asset_id, text]]；TinyTroupeBackend 经
    episodic_memory.store 注入。"""

# orchestrator/world.py
def build_scene_config(store, character_ids, location_id, dm=None,
                       pins=None,
                       memories: dict[str, str] | None = None) -> dict:
    """memories 非 None 时角色卡 character 加 memory 键（空串不加）。"""

def run_world(..., memory_from: str | None = None) -> list[dict]:
    """memory_from 非 None：从 interlude_memories 取交集角色记忆，
    seed 后端 + 注入角色卡；差集角色跳过并在返回前不做任何记忆动作。"""
```

## 3. MCP 工具（mcp_server.py 追加）

```python
def generate_interlude_memory(run_id: str, character_ids: list[str],
                              channel: str = "template",
                              regenerate: bool = False) -> dict:
    """生成/复用幕间记忆。返回 {memories: [...], skipped: [...]}。
    RunNotFound；channel 非法 → BadChannel。"""

def get_interlude_memory(run_id: str,
                         asset_id: str | None = None) -> dict:
    """读取记忆。返回 {memories: [{asset_id, revision, summary,
    event_refs, channel, tokens_in, tokens_out, created_at}]}。"""

# 既有工具扩参（缺省 None = 现状逐键一致）：
def create_world(..., memory_from: str | None = None) -> dict
    # config 冻结增加 memory_from 键
def run_simulation(..., memory_from: str | None = None) -> dict
def reshoot(..., memory_from: str | None = None) -> dict
    # reshoot 缺省沿用世界 config 已冻结的 memory_from
```

错误词汇沿用 007/011：`RunNotFound` / `BadChannel` / `InterludeError`。

## 4. 配置键（.env.example）

| 键 | 默认 | 说明 |
|----|------|------|
| `INTERLUDE_MAX_EVENTS` | 50 | llm 通道输入事件数上限（新近优先） |
| `INTERLUDE_MAX_CHARS` | 4000 | 单条事件转写截断 |

## 5. 测试契约

- `tests/contract/test_interlude.py`：三规则逐条（含 inner_voice 私有 +
  visible_to 定向 + 公开）/ template 确定性可重复 / 幂等复用 tokens=0 /
  regenerate 升版 / 空事件空摘要 / 跨戏交集 skipped / 注入两路断言
  （config memory 键 + Mock 后端 seeded）/ 不传 memory_from 兼容锚点。
- `test_mcp_server.py` 追加：两工具 + 三扩参；错误词汇。
- 全部离线零外部调用；既有测试无回归。
