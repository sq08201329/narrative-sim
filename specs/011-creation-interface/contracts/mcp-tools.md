# Contract: MCP 创作队工具（011）

**Feature**: 011-creation-interface | **Date**: 2026-10-21

本契约先行于实现（宪章 I）。所有工具挂在既有 `build_server()` 实例上，
错误统一 `ToolError("{类型}: {原因}")`（007 口径）。

## 错误词汇表

`AssetNotFound` / `RunNotFound` / `WorldNotFound` / `RevisionNotFound` /
`RevisionConflict` / `HandoffExists` / `BriefError`（009 既有）/
`DMConfigError`（010 既有）

## 读工具（US1）

```python
def list_assets(type: str | None = None) -> dict:
    """列出资产概要。返回 {assets: [{asset_id, type, name, status,
    current_revision, created_at}]}，按 asset_id 排序。"""

def get_asset(asset_id: str) -> dict:
    """读资产完整卡。返回资产全字段 + current_revision +
    secrecy 标注键（secret 为创作可见/仿真不可见）。AssetNotFound。"""

def get_materials(asset_id: str) -> dict:
    """读资产调研原料。返回 {materials: [{id, query, retriever, context,
    created_at}]}；无原料返回空列表。"""

def search_materials(keyword: str) -> dict:
    """原料全文关键词检索（query/context 子串匹配，大小写不敏感）。
    返回 {materials: [...同 get_materials 结构, + asset_id]}。"""

def get_events(run_id: str) -> dict:
    """直接返回事件列表（与 export_events 文件同口径同校验）。
    返回 {events: [...]}。RunNotFound。"""

def get_world_state(world_id: str) -> dict:
    """返回 {tick, state} 最新快照；无快照返回 {tick: None, state: None}。
    WorldNotFound（无 config 时）。"""

def list_dm_calls(run_id: str) -> dict:
    """返回 {dm_calls: [...]}（字段同 010 dm_calls 表）。RunNotFound。"""
```

## 写工具：修订与回滚（US2）

```python
def revise_asset(asset_id: str, patch: dict, reason: str,
                 author: str = "creation-agent",
                 base_revision: int | None = None) -> dict:
    """merge patch 语义（深合并，值为 None 删键）应用到当前版 → 新修订版。
    base_revision 非 None 且与当前指针不符 → RevisionConflict（乐观锁）。
    返回 {asset_id, revision, impacted: [{world_id, pinned_revision,
    run_ids: [...]}], warning: str | None}
    impacted 非空时 warning 固定文案提示历史 run 使用旧版。
    AssetNotFound；patch 非 dict 或为空 → ToolError("BadPatch: ...")。"""

def rollback_asset(asset_id: str, to_revision: int) -> dict:
    """当前指针回指 to_revision，payload 回填该版快照，历史不删。
    返回 {asset_id, current_revision, stale_worlds: [world_id...]}
    （stale_worlds = 冻结了高于 to_revision 版号的世界）。
    AssetNotFound / RevisionNotFound。"""
```

## 写工具：移交与重拍（US3/US4）

```python
def export_handoff(world_id: str, out_dir: str = "handoff",
                   run_id: str | None = None, overwrite: bool = False) -> dict:
    """导出移交目录（布局见 data-model.md）。run_id 缺省取该世界最近 run；
    无 run 时 events/dm_calls 为空集合。out_dir/world_id 已存在且
    overwrite=False → HandoffExists。
    返回 {dir, manifest, counts}。WorldNotFound。"""

def reshoot(world_id: str, new_run_id: str, ticks: int,
            use_latest: bool = False, backend: str = "mock",
            dm: bool = False) -> dict:
    """重拍：use_latest=False 用世界冻结 pin 原样重跑；True 重钉到当前版
    （更新 worlds.config 的 revisions）再跑。产出新 run，事件编号全局连续。
    返回 {run_id, event_count, revision_pins}。WorldNotFound /
    RunExists（new_run_id 已存在）。"""
```

## 既有工具扩参

```python
def run_simulation(world_id, run_id, ticks, backend="tinytroupe",
                   resume=False, dm: bool = False,
                   dm_max_calls: int = 50,
                   dm_knowledge_chars: int = 2000) -> dict:
    """dm=True 启用真实裁决（010）；返回增加 dm_calls/failed 计数。
    缺省 dm=False 行为与 007 版逐键一致。"""

def research_brief(theme: str) -> dict:
    """009 立项调研：题材 → 三类清单 → 批量执行入库。
    返回 {brief, ledger}（ledger 每条 {query, status, asset_id?}）。
    注意：每条调研一次外部调用，分钟级耗时（成本见宪章 VI）。"""
```

## 业务模块契约（orchestrator/revision.py / handoff.py）

```python
# revision.py
class RevisionError(RuntimeError): ...        # RevisionConflict/RevisionNotFound 基类
def revise(store, asset_id, patch, reason, author, base_revision) -> dict
def rollback(store, asset_id, to_revision) -> dict
def impacted_runs(store, asset_id) -> list[dict]   # worlds.config pin 反查

# store.py 新原语
def put_revision(asset_id, payload, patch, reason, author) -> int  # 返回新 revision
def get_revision(asset_id, revision) -> dict       # RevisionNotFound
def list_revisions(asset_id) -> list[dict]         # 按 revision 升序
def get_asset_at_revision(asset_id, revision) -> dict
def set_current_revision(asset_id, revision) -> None

# handoff.py
def export_handoff(store, world_id, out_dir, run_id=None, overwrite=False) -> dict
```

## 测试契约

- `tests/contract/test_revision.py`：revise 升版/merge patch 语义/乐观锁冲突/
  回滚回填/stale 标记/revision 0 自动建立/**三冻结面逐字节断言**（修订前后
  原料表、事件表、他世界 config 不变）。
- `tests/contract/test_handoff.py`：目录结构/manifest 计数与 sha256 一致/
  空世界导出/覆盖拒绝/secret 密级标注存在。
- `test_mcp_server.py` 追加：新工具经 fastmcp Client 调用、错误词汇断言、
  run_simulation dm=False 兼容锚点。
- 全部离线零外部调用；既有测试无回归。
