# Quickstart: DM 裁判启用验证

**Feature**: 010-dm-adjudicator | **Date**: 2026-10-21

## 离线验证（默认测试集，零外部调用）

```bash
uv run pytest -m "not real" -q
```

预期：既有 130 项无回归 + 新增契约测试全绿。重点断言（见
`tests/contract/test_dm_adjudicator.py`）：

1. `dm=None` 时 `build_scene_config` 输出与 006 版一致（兼容锚点）。
2. 传入 DMOptions 后：`actions.act.dm` 存在且含 hint/白名单/上限；
   `scene.max_dm_calls` 生效；`scene.dm_knowledge` 含原料要点且不超预算。
3. MockDMProvider 驱动下：act 动作产生 dm_calls 审计行（effects/narrative/
   tokens 字段齐备），效果落入世界状态快照。
4. FailingMockDMProvider 连续失败：run 正常结束，dm_calls 含 `failed=1` 行。
5. `build_dm_provider` 无密钥抛 DMConfigError 且消息含缺失键名。

## 真机验收（real 标记）

前置：环境有 `DEEPSEEK_API_KEY` 与 `DEEPSEEK_BASE_URL=https://api.deepseek.com`。

**模型注意**：裁决必须用非思考模型（默认 `DM_MODEL=deepseek-chat`）。
deepseek-flash 是思考模型，拒绝 instructor 的 tool_choice，裁决会全败
（降级兜底，不崩溃但无真实裁决）。TinyTroupe 后端协议只有 THINK/TALK/DONE，
不产出 act 动作——验收裁决链路用 `--mock` 后端（内置剧本 tick1/tick4 出
act），与 TinyTroupe 的共存由不带 --mock 的 run 验证（零裁决、正常运行）。

```bash
# 1. 真实裁决链路：mock 后端（内置剧本产生 act 动作）+ 真实 DM
uv run python scripts/run_world_chain.py --db dm_accept.db \
  --run-id dm_r1 --world-id world_dm1 --ticks 4 --mock --dm --dm-max-calls 20

# 2. 查看裁决审计
uv run python -c "from orchestrator.store import Store; \
import json; s=Store('dm_accept.db'); \
[print(json.dumps(r, ensure_ascii=False)[:200]) for r in s.list_dm_calls('dm_r1')]"
```

预期结果（对应 SC-001/002/004）：

- `dm_calls` 行数 = act 动作提交次数（mock 剧本 4 tick = 4 次，100% 覆盖）。
- 效果非空且在白名单内（实测多为 emit_event 后果事件；`set` 落快照由离线
  测试 test_act_adjudicated_effects_and_audit 覆盖）。
- `narrative` 只描述行动者与世界，不出现其他角色的言行。
- run 正常结束（`finish_run` 状态 done）。

真机实测记录（2026-10-21，dm_r3）：4/4 成功，单次约 2500+120 token，
叙事贴合场景细节；一次越界效果（create_entity）被引擎拒绝并携带反馈
重试成功——重试回路真机生效。

## 史料注入验证（可选，需 009 原料）

用 `yanyu.db`（已有皇城司调研原料）跑 `--dm`，检查裁决叙事与史料一致
（如侦缉手段相关判定不违背原料描述），人工核对（SC-002 后半）。

## 故障注入验收

用 `--mock` 后端隔离角色链路（TinyTroupe 与裁决共用模型出口，错误地址会
同时打断两者），仅让裁决服务不可达：

```bash
DEEPSEEK_BASE_URL=http://127.0.0.1:9 uv run python scripts/run_world_chain.py \
  --db dm_fault.db --run-id dm_f1 --world-id world_f1 --ticks 3 --mock --dm
```

预期：run 完成率 100%（exit 0），dm_calls 全为 `failed=1`，事件流含兜底
叙事（SC-004）。真机实测通过（2026-10-21：2/2 failed，契约校验全过）。
