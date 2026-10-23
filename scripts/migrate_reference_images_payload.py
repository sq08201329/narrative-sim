"""一次性迁移（已执行）：剥离当前 assets.payload 里的 reference_images 字段。

== 元信息 ==
- 做什么：把 `reference_images` 从资产的**当前** payload 里剥离，改为由
  `image_generations` 表派生（Store.get_asset / Store.reference_images）。
  只改当前 payload；`asset_revisions` 历史行**原样保留**（历史记录不重写）。
  若 payload 里有图但 image_generations 没有对应记录（历史遗留），先回填一条
  `provider=backfill` 的出图记录，保证派生结果不丢图。
- 什么时候跑的：2026-10-22 22:30:58（A1 落地同批；服务停库后执行）
- 跑过的库：`data/library.db`、`data/projects/linan.db`
- 备份文件名（迁移前整库拷贝，与库同目录）：
  - `data/library.db.pre_refimg_strip.20261022223058.bak`
  - `data/projects/linan.db.pre_refimg_strip.20261022223058.bak`
  - 另有一次半程备份 `data/library.db.pre_refimg_strip.20261022223044.bak`
    （撞到 `prop_1a5efe109f` 缺修订行中断，未动项目库，修复后重跑）
- 跑完怎么核对：
  1) 每个资产 `Store.reference_images(aid)` 的张数应与迁移前 payload 里的张数一致；
  2) `Store.get_asset(aid)` 仍有 `reference_images`，但当前 payload 的原文里没有该键；
  3) 历史修订（`Store.get_revision(aid, N)`）仍保留该键；
  4) `worlds.tick` / runs / events 数不变。
  实例：迁移后 library 察子 1 张；项目库察子 13 张、刘七郎 2 张、新场景 3 张；
  `world_linan_ep01` tick 6、`run_linan_ep01_full` 14 条事件不变。

== 定位 ==
**历史留档脚本**，不是 CLI 入口、不被任何模块 import。库结构再变时不要复用，
按当时的实际情况重写并另立备份。

用法（只在明确需要重放时，先停服务、先备份）：
    .venv\\Scripts\\python.exe scripts\\migrate_reference_images_payload.py data\\library.db
"""
import hashlib
import json
import shutil
import sys
import time

sys.path.insert(0, ".")
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from db.init_db import init as init_db  # noqa: E402
from orchestrator.store import Store  # noqa: E402


def _sha_file(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def migrate(db: str) -> None:
    init_db(db)
    stamp = time.strftime("%Y%m%d%H%M%S")
    backup = f"{db}.pre_refimg_strip.{stamp}.bak"
    shutil.copy2(db, backup)
    print(f"DB={db}")
    print(f"BACKUP={backup}")

    store = Store(db)
    try:
        assets = store.list_asset_summaries()
        for a in assets:
            aid = a["asset_id"]
            cur = int(a["current_revision"])
            # 011 前存量资产可能没有修订行：先补建 revision0（幂等）
            if not store.list_revisions(aid):
                store.ensure_revision0(aid)
                print(f"ENSURE_REV0={aid}")
            raw = json.loads(store.get_revision(aid, cur)["payload"])
            refs = list(raw.get("reference_images") or [])
            derived_before = store.reference_images(aid)
            backfilled = 0
            for path in refs:
                if path in derived_before:
                    continue
                sha = _sha_file(path)
                store.put_image_generation(
                    aid, "legacy-backfill", 1, "legacy",
                    [path], [sha], "backfill", cur)
                backfilled += 1
            derived_after = store.reference_images(aid)
            stripped = 0
            if refs:
                # 走 Store 唯一入口：set_current_revision 回填该版快照时会
                # 剥离 reference_images（A1 口径），不直连 sqlite3。
                store.set_current_revision(aid, cur)
                # 审计读：确认「当前 payload」已无该键（历史修订行不查）
                row = store._conn.execute(
                    "SELECT payload FROM assets WHERE asset_id=?",
                    (aid,)).fetchone()
                if "reference_images" in json.loads(row["payload"]):
                    raise RuntimeError(
                        f"剥离失败（当前 payload 仍有该键）: {aid}@{cur}")
                stripped = len(refs)
            print(f"ASSET={aid} rev={cur} refs_in_payload={len(refs)} "
                  f"derived_before={len(derived_before)} "
                  f"backfilled={backfilled} "
                  f"derived_after={len(derived_after)} "
                  f"stripped={stripped}")
    finally:
        store.close()
    print("DONE", db)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    for target in sys.argv[1:]:
        migrate(target)
