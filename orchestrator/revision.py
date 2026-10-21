"""资产修订版本化业务（011 US2，宪章 II 胶水层）。

- revise：merge patch 深合并 → put_revision → impacted 使用留痕（R3）
- rollback：指针回指 + 快照回填，历史不删；stale_worlds 标记（R1）
- 三冻结面（FR-009）由调用路径保证：本模块只写 asset_revisions 与
  assets 两表，永不动原料表/事件表/世界 config
"""
import json

from .store import Store


class RevisionError(RuntimeError):
    """修订业务错误基类。"""


class RevisionConflict(RevisionError):
    """乐观锁冲突：base_revision 与当前指针不符。"""


class RevisionNotFound(RevisionError):
    """目标修订版不存在。"""


def _merge_patch(base, patch):
    """RFC 7386 风格深合并：dict 递归，None 删键，其余整体替换。"""
    if not isinstance(patch, dict) or not isinstance(base, dict):
        return base if patch is None else patch
    out = dict(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_patch(out[k], v)
        else:
            out[k] = v
    return out


def impacted_runs(store: Store, asset_id: str) -> list[dict]:
    """反查 worlds.config 的 revisions pin：哪些世界钉了该资产的哪版。"""
    out = []
    for w in store.list_world_configs():
        pins = w["config"].get("revisions") or {}
        if asset_id not in pins:
            continue
        out.append({
            "world_id": w["world_id"],
            "pinned_revision": pins[asset_id],
            "run_ids": store.list_runs(w["world_id"]),
        })
    return out


def revise(store: Store, asset_id: str, patch: dict, reason: str,
           author: str = "creation-agent",
           base_revision: int | None = None) -> dict:
    """merge patch 应用到当前版 → 新修订版；响应带 impacted 使用留痕。"""
    if not isinstance(patch, dict) or not patch:
        raise RevisionError("BadPatch: patch 必须是非空 dict")
    try:
        current = store.get_asset(asset_id)
    except KeyError:
        raise KeyError(f"资产不存在: {asset_id}") from None
    cur_rev = store.current_revision(asset_id)
    if base_revision is not None and base_revision != cur_rev:
        raise RevisionConflict(
            f"base_revision={base_revision} 与当前版 r{cur_rev} 不符，"
            f"请重读后重新提交")

    merged = _merge_patch(current, patch)
    merged["asset_id"] = asset_id
    payload = json.dumps(merged, ensure_ascii=False)
    new_rev = store.put_revision(
        asset_id, payload,
        json.dumps(patch, ensure_ascii=False), reason, author)

    impacted = impacted_runs(store, asset_id)
    warning = None
    if impacted:
        worlds = "、".join(i["world_id"] for i in impacted)
        warning = (f"资产已被世界引用（{worlds}），其 run 使用的是冻结版卡；"
                   f"修订不影响历史，重拍或新建世界才会用新版")
    return {"asset_id": asset_id, "revision": new_rev,
            "impacted": impacted, "warning": warning}


def rollback(store: Store, asset_id: str, to_revision: int) -> dict:
    """指针回指目标版，payload 回填快照；历史不删。"""
    try:
        store.get_revision(asset_id, to_revision)
    except KeyError:
        raise RevisionNotFound(
            f"修订版不存在: {asset_id}@r{to_revision}") from None
    store.set_current_revision(asset_id, to_revision)
    stale = [i["world_id"] for i in impacted_runs(store, asset_id)
             if isinstance(i["pinned_revision"], int)
             and i["pinned_revision"] > to_revision]
    return {"asset_id": asset_id, "current_revision": to_revision,
            "stale_worlds": stale}
