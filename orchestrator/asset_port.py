"""素材搬运（asset_port）：把一个资产（含全部修订与原料）在主库与项目库之间搬。

宪章 II 胶水层：只组合 Store 既有读方法与导入专用写入方法
（import_asset_row / upsert_revision_at / put_material），
**只碰 assets / asset_revisions / research_materials 三张表**。

用法见 scripts/asset_port.py（export / import / verify）。
"""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .store import Store

FORMAT = "narrative-sim-asset-port/1"
VALID_TYPES = ("character", "prop", "scene", "epoch")
IMPORT_TABLES = ("assets", "asset_revisions", "research_materials")


class AssetPortError(RuntimeError):
    """搬运失败基类（退出码 1）。"""


class BundleCorrupt(AssetPortError):
    """bundle 文件损坏：格式/字段/哈希/资产类型不符（退出码 2）。"""


class ManualAssetRejected(AssetPortError):
    """手写资产（provenance=manual）默认拒绝导入。"""


class RevisionConflict(AssetPortError):
    """同号修订内容不同（或指针不一致）。"""


class DstAhead(AssetPortError):
    """目标库修订领先于 bundle，拒绝导入。"""


class DstBehind(AssetPortError):
    """目标库修订落后于 bundle，需 --allow-extend。"""


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def _sha(obj) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _loads(text: str):
    try:
        return json.loads(text)
    except ValueError as e:
        raise BundleCorrupt(f"payload 不是合法 JSON: {e}") from e


def _bundle_fingerprint(asset: dict, revisions: list[dict],
                        materials: list[dict], provenance: str) -> dict:
    body = {"format": FORMAT, "asset": asset, "revisions": revisions,
            "materials": materials, "provenance": provenance}
    return {
        "asset_sha256": asset["payload_sha256"],
        "revisions_sha256": _sha(revisions),
        "materials_sha256": _sha(materials),
        "bundle_sha256": _sha(body),
    }


def build_bundle(store: Store, asset_id: str) -> dict:
    """从库中打包一个资产（行 + 全部修订 + 该资产全部原料）。"""
    row = next((r for r in store.list_asset_summaries()
                if r["asset_id"] == asset_id), None)
    if row is None:
        raise AssetPortError(f"资产不存在: {asset_id}")
    if row["type"] not in VALID_TYPES:
        raise BundleCorrupt(f"非法资产类型: {row['type']}")

    payload = store.get_asset(asset_id)
    revisions = []
    for rev in store.list_revisions(asset_id):
        body = _loads(rev["payload"])
        revisions.append({
            "revision": int(rev["revision"]),
            "payload": body,
            "payload_sha256": _sha(body),
            "patch": rev.get("patch"),
            "reason": rev.get("reason") or "",
            "author": rev.get("author") or "system",
            "created_at": rev.get("created_at"),
        })
    materials = []
    for m in store.get_materials(asset_id):
        materials.append({
            "query": m["query"],
            "retriever": m["retriever"],
            "context": m["context"],          # 原样，不截断、不清洗
            "context_sha256": _sha_text(m["context"]),
            "created_at": m.get("created_at"),
        })
    revisions.sort(key=lambda r: r["revision"])
    materials.sort(key=lambda m: (m["query"], m.get("created_at") or "",
                                  m["context_sha256"]))

    prov = payload.get("provenance") or {}
    manual = (prov.get("retriever") == "manual"
              or prov.get("model") in (None, "none"))
    asset = {
        "asset_id": row["asset_id"],
        "type": row["type"],
        "name": row["name"],
        "status": row["status"],
        "current_revision": int(row["current_revision"]),
        "payload": payload,
        "payload_sha256": _sha(payload),
    }
    provenance = "manual" if manual else "researched"
    return {
        "format": FORMAT,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset,
        "revisions": revisions,
        "materials": materials,
        "provenance": provenance,
        "fingerprint": _bundle_fingerprint(asset, revisions, materials,
                                           provenance),
    }


def export_asset(store: Store, asset_id: str, out_path: str) -> dict:
    """导出 bundle 到 out_path，返回摘要。"""
    bundle = build_bundle(store, asset_id)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return {
        "path": str(path),
        "asset_id": bundle["asset"]["asset_id"],
        "provenance": bundle["provenance"],
        "revisions": len(bundle["revisions"]),
        "materials": len(bundle["materials"]),
        "bundle_sha256": bundle["fingerprint"]["bundle_sha256"],
    }


def load_bundle(path: str) -> dict:
    """读取并逐段校验 bundle；任何不符都判为 BundleCorrupt。"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise BundleCorrupt(f"读不到 bundle 文件: {e}") from e
    try:
        bundle = json.loads(text)
    except ValueError as e:
        raise BundleCorrupt(f"bundle 不是合法 JSON: {e}") from e
    if not isinstance(bundle, dict):
        raise BundleCorrupt("bundle 顶层必须是对象")
    if bundle.get("format") != FORMAT:
        raise BundleCorrupt(
            f"format 不符: {bundle.get('format')!r}（期望 {FORMAT}）")

    asset = bundle.get("asset")
    revisions = bundle.get("revisions")
    materials = bundle.get("materials")
    prov = bundle.get("provenance")
    fingerprint = bundle.get("fingerprint")
    for key, val, typ in (("asset", asset, dict),
                          ("revisions", revisions, list),
                          ("materials", materials, list),
                          ("fingerprint", fingerprint, dict)):
        if not isinstance(val, typ):
            raise BundleCorrupt(f"缺少或类型错误的字段: {key}")
    if prov not in ("researched", "manual"):
        raise BundleCorrupt(f"provenance 非法: {prov!r}")

    if asset.get("type") not in VALID_TYPES:
        raise BundleCorrupt(f"非法资产类型: {asset.get('type')!r}")
    if not asset.get("asset_id"):
        raise BundleCorrupt("asset.asset_id 缺失")
    if not isinstance(asset.get("payload"), dict):
        raise BundleCorrupt("asset.payload 必须是对象")
    if _sha(asset["payload"]) != asset.get("payload_sha256"):
        raise BundleCorrupt("asset.payload_sha256 不符（文件被改动）")
    if not isinstance(asset.get("current_revision"), int):
        raise BundleCorrupt("asset.current_revision 必须是整数")

    seen = set()
    for rev in revisions:
        if not isinstance(rev, dict):
            raise BundleCorrupt("revisions 元素必须是对象")
        num = rev.get("revision")
        if not isinstance(num, int) or num < 0:
            raise BundleCorrupt(f"revision 非法: {num!r}")
        if num in seen:
            raise BundleCorrupt(f"revision 重复: {num}")
        seen.add(num)
        if not isinstance(rev.get("payload"), dict):
            raise BundleCorrupt(f"r{num}.payload 必须是对象")
        if _sha(rev["payload"]) != rev.get("payload_sha256"):
            raise BundleCorrupt(f"r{num}.payload_sha256 不符（文件被改动）")
    if asset["current_revision"] not in seen:
        raise BundleCorrupt(
            f"current_revision {asset['current_revision']} 不在 revisions 内")

    for m in materials:
        if not isinstance(m, dict):
            raise BundleCorrupt("materials 元素必须是对象")
        if not isinstance(m.get("context"), str):
            raise BundleCorrupt("material.context 必须是字符串")
        if _sha_text(m["context"]) != m.get("context_sha256"):
            raise BundleCorrupt("material.context_sha256 不符（文件被改动）")

    expected = _bundle_fingerprint(asset, revisions, materials, prov)
    for key, val in expected.items():
        if fingerprint.get(key) != val:
            raise BundleCorrupt(f"fingerprint.{key} 不符（文件被改动）")
    return bundle


def verify_bundle(store: Store, path: str) -> dict:
    """核对 bundle 在目标库是否一一对齐。dst 多出的内容记 extra，不算失败。"""
    bundle = load_bundle(path)
    asset = bundle["asset"]
    aid = asset["asset_id"]
    rows = {r["asset_id"]: r for r in store.list_asset_summaries()}
    dst = rows.get(aid)
    result = {"asset_id": aid, "ok": True, "provenance": bundle["provenance"],
              "asset": {}, "revisions": {}, "materials": {}}

    if dst is None:
        result["asset"] = {"status": "missing"}
        result["ok"] = False
    else:
        same_payload = _sha(store.get_asset(aid)) == asset["payload_sha256"]
        same_pointer = dst["current_revision"] == asset["current_revision"]
        status = "ok" if (same_payload and same_pointer) else "mismatch"
        result["asset"] = {"status": status,
                           "current_revision": dst["current_revision"],
                           "expected_revision": asset["current_revision"]}
        result["ok"] = result["ok"] and status == "ok"

    if dst is None:
        dst_revs = {}
    else:
        dst_revs = {int(r["revision"]): _sha(_loads(r["payload"]))
                    for r in store.list_revisions(aid)}
    src_revs = {r["revision"]: r["payload_sha256"]
                for r in bundle["revisions"]}
    missing = sorted(set(src_revs) - set(dst_revs))
    extra = sorted(set(dst_revs) - set(src_revs))
    mismatch = sorted(n for n in set(src_revs) & set(dst_revs)
                      if src_revs[n] != dst_revs[n])
    result["revisions"] = {"missing": missing, "extra": extra,
                           "mismatch": mismatch, "total": len(src_revs)}
    if missing or mismatch:
        result["ok"] = False

    src_mats = {(m["query"], m["retriever"], m["context_sha256"])
                for m in bundle["materials"]}
    if dst is None:
        dst_mats = set()
    else:
        dst_mats = {(m["query"], m["retriever"], _sha_text(m["context"]))
                    for m in store.get_materials(aid)}
    mat_missing = sorted(src_mats - dst_mats)
    mat_extra = sorted(dst_mats - src_mats)
    result["materials"] = {"missing": len(mat_missing),
                           "extra": len(mat_extra),
                           "total": len(src_mats)}
    if mat_missing:
        result["ok"] = False
    return result


def import_bundle(store: Store, path: str, allow_extend: bool = False,
                  allow_manual: bool = False, backup: bool = True,
                  dry_run: bool = False, db_path: str | None = None) -> dict:
    """把 bundle 导入目标库。

    幂等：内容一致的整体跳过；原料按 (query, retriever, context 哈希) 去重。
    冲突（同号不同内容、dst 领先、指针不一致）报错且不写任何东西。
    """
    bundle = load_bundle(path)
    asset = bundle["asset"]
    aid = asset["asset_id"]

    if bundle["provenance"] == "manual" and not allow_manual:
        raise ManualAssetRejected(
            f"资产 {aid} 的 provenance=manual（无调研来源），默认拒绝导入；"
            "确需导入请加 --allow-manual")

    rows = {r["asset_id"]: r for r in store.list_asset_summaries()}
    dst = rows.get(aid)
    src_revs = {r["revision"]: r["payload_sha256"]
                for r in bundle["revisions"]}
    dst_revs = ({int(r["revision"]): _sha(_loads(r["payload"]))
                 for r in store.list_revisions(aid)} if dst else {})

    action = "insert"
    missing: list[int] = []
    if dst is not None:
        shared = set(src_revs) & set(dst_revs)
        bad = sorted(n for n in shared if src_revs[n] != dst_revs[n])
        if bad:
            raise RevisionConflict(
                f"修订冲突: {aid}@r{bad[0]}（同号不同内容），拒绝覆盖")
        extra = sorted(set(dst_revs) - set(src_revs))
        if extra:
            raise DstAhead(
                f"目标库领先: {aid} 多出修订 {extra}，拒绝导入（不降级）")
        missing = sorted(set(src_revs) - set(dst_revs))
        if not missing:
            if dst["current_revision"] != asset["current_revision"]:
                raise RevisionConflict(
                    f"指针不一致: {aid} dst=r{dst['current_revision']} "
                    f"bundle=r{asset['current_revision']}")
            action = "identical"
        elif not allow_extend:
            raise DstBehind(
                f"目标库落后: {aid} 缺修订 {missing}；"
                "确认要补齐请加 --allow-extend")
        else:
            action = "extend"

    if dst is None:
        existing = set()
    else:
        existing = {(m["query"], m["retriever"], _sha_text(m["context"]))
                    for m in store.get_materials(aid)}
    new_materials = [m for m in bundle["materials"]
                     if (m["query"], m["retriever"],
                         m["context_sha256"]) not in existing]

    plan = {
        "asset_id": aid,
        "action": action,
        "provenance": bundle["provenance"],
        "revisions_total": len(bundle["revisions"]),
        "revisions_missing": missing,
        "materials_total": len(bundle["materials"]),
        "materials_missing": len(new_materials),
        "backup": None,
        "revisions_added": 0,
        "materials_added": 0,
    }
    if dry_run:
        return plan

    if backup and db_path and Path(db_path).exists():
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = f"{db_path}.pre_import.{stamp}.bak"
        shutil.copy2(db_path, backup_path)
        plan["backup"] = backup_path

    if action in ("insert", "extend"):
        revisions = (bundle["revisions"] if action == "insert"
                     else [r for r in bundle["revisions"]
                           if r["revision"] in set(missing)])
        store.import_asset_row({
            "asset_id": aid,
            "type": asset["type"],
            "name": asset["name"],
            "status": asset["status"],
            "payload": asset["payload"],
            "current_revision": asset["current_revision"],
        }, revisions)
        plan["revisions_added"] = len(revisions)

    for m in new_materials:
        store.put_material(aid, m["query"], m["retriever"], m["context"])
    plan["materials_added"] = len(new_materials)
    return plan
