# Quickstart: 幕间记忆传递验证

**Feature**: 012-interlude-memory | **Date**: 2026-10-21

## 离线验证（默认测试集，零外部调用）

```bash
uv run pytest -m "not real" -q
```

预期：既有 169 项无回归 + 新增测试全绿。重点断言：

1. 过滤三规则：inner_voice 仅本人可见；visible_to 定向事件他人零泄漏
   （SC-001）；公开事件全员可见。
2. template 通道两次生成结果逐字节一致（确定性）。
3. 幂等：第二次 generate 同键复用，tokens=0，reused=True；regenerate
   升 revision，旧版可取。
4. 注入：run_world(memory_from=...) 后 scene config 角色卡含 memory 键，
   Mock 后端 seeded 记录与记忆文本一致；不传时输出与现状逐键一致。
5. MCP：generate/get_interlude_memory + 三工具 memory_from 参数；
   RunNotFound/BadChannel 错误词汇。

## 真机验收（real，SC-002）

前置：`DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL`；以上一幕既有 run
（如 world_talk.db 的 talk_r1）为记忆来源：

```bash
# 1. 生成记忆（llm 通道，每角色一次调用；第二次跑应全复用零计费）
NARRATIVE_DB=world_talk.db uv run python -c "
from orchestrator.store import Store
from orchestrator.interlude import generate_memories
s = Store('world_talk.db')
ms = generate_memories(s, 'talk_r1', ['char_su_wanqing', 'char_shen_ke'],
                       channel='llm')
for m in ms: print(m['asset_id'], m['revision'], m['summary'][:80])
"
# 2. 第二幕带记忆起跑（TinyTroupe 真后端）
#    create_world(memory_from='talk_r1') → run_simulation
# 3. 人工核对：第二幕角色对白/内省引用上一幕经历（至少 1 处）
```

## 故障与边界

- 来源 run 不存在：InterludeError，不落任何半成品。
- 无事件 run：空摘要落库（显式空语义），下一幕正常起跑。
- llm 通道服务失败：报错且不落库；已有记忆不受影响。
