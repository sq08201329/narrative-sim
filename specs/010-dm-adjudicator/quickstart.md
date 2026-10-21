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

前置：环境有 `DEEPSEEK_API_KEY`；复用 008 演示库 `world_talk.db`
（沈刻对手戏资产）或任一含 ≥1 角色 + 场景的库。

```bash
# 1. 启用裁决跑 6 tick（成本帽 20）
uv run python scripts/run_world_chain.py --db world_talk.db \
  --run dm_r1 --world world_dm1 --chars <char_id_1> <char_id_2> \
  --location <scene_id> --ticks 6 --dm --dm-max-calls 20

# 2. 查看裁决审计
uv run python -c "from orchestrator.store import Store; \
import json; s=Store('world_talk.db'); \
[print(json.dumps(r, ensure_ascii=False)[:200]) for r in s.list_dm_calls('dm_r1')]"
```

预期结果（对应 SC-001/002/004）：

- `dm_calls` 行数 = act 动作提交次数（100% 覆盖，无静默丢失）。
- 至少一行 `effects` 非空（非平凡状态变更），快照中可见对应属性变化。
- `narrative` 只描述行动者与世界，不出现其他角色的言行。
- run 正常结束（`finish_run` 状态 done）；若有失败行，`failed=1` 且 run
  未中断。

## 史料注入验证（可选，需 009 原料）

用 `yanyu.db`（已有皇城司调研原料）跑 `--dm`，检查裁决叙事与史料一致
（如侦缉手段相关判定不违背原料描述），人工核对（SC-002 后半）。

## 故障注入验收

临时把 `DEEPSEEK_BASE_URL` 指向不可达地址跑 `--dm`：run 完成率 100%，
dm_calls 全为 `failed=1`，事件流含兜底叙事（SC-004）。
