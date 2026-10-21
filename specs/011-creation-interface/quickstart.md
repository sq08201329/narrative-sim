# Quickstart: 创作队对接接口验证

**Feature**: 011-creation-interface | **Date**: 2026-10-21

## 离线验证（默认测试集，零外部调用）

```bash
uv run pytest -m "not real" -q
```

预期：既有 141 项无回归 + 新增契约测试全绿。重点断言：

1. 修订闭环：revise → get_asset 读回新版 → list_revisions 两版齐全 →
   rollback → 读回 revision 0 内容；**原料表/事件表/他世界 config 逐字节
   不变**（FR-009 污染防线）。
2. 乐观锁：base_revision 过期 → RevisionConflict；回滚不存在版 →
   RevisionNotFound。
3. 版号锚点：create_world 冻结 revisions；修订后 run_simulation 仍按 pin
   取旧卡；reshoot(use_latest=True) 后新 run 用新卡，event_id 与旧 run
   零冲突。
4. 移交包：manifest 每项 sha256 与文件实算一致；counts 与库内一致；
   空世界 events/dm_calls 为空数组；HandoffExists 拒绝覆盖。
5. MCP 读工具：经 fastmcp Client 全读路径（list→get→materials→events→
   state→dm_calls），不存在对象返回结构化错误词汇。

## 真机联调（可选）

启动服务：`uv run python scripts/run_mcp_server.py`（127.0.0.1:8300），
用任一 MCP 客户端对 `yanyu.db`（设 `NARRATIVE_DB=yanyu.db`）：

```text
list_assets → get_asset("char_e8301d6530") → get_materials(同id)
→ revise_asset（微调 personality）→ export_handoff("world_id") 
→ 检查 handoff/ 目录
```

预期：修订后 run_simulation 原世界仍用旧卡（pin 生效）；移交包
materials/ 含皇城司原料 md；manifest revision_pins 与库内一致。

## 重拍演示（离线）

```bash
uv run pytest tests/contract/test_revision.py -k reshoot -q
```

预期：同世界两版 run 并存，事件编号全局连续，导出可 diff。
