"""US3 接缝验证 2：数据库唯一通路 —— store.py 之外不得直连 sqlite3。

覆盖 spec：FR-005 / SC-005；宪章原则 III（存储单一入口）。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SCAN_DIRS = ["scripts", "tests", "orchestrator"]
SELF = ROOT / "tests" / "contract" / "test_single_store_path.py"
ALLOWED = {ROOT / "orchestrator" / "store.py", ROOT / "db" / "init_db.py", SELF}

# 直连信号：import sqlite3、sqlite3.connect、.execute( 裸 SQL
PATTERNS = [
    re.compile(r"import\s+sqlite3"),
    re.compile(r"sqlite3\.connect"),
]


def test_no_direct_sqlite_outside_store():
    offenders = []
    for d in SCAN_DIRS + ["db"]:
        for py in (ROOT / d).rglob("*.py"):
            if py in ALLOWED:
                continue
            text = py.read_text(encoding="utf-8")
            for pat in PATTERNS:
                for match in pat.finditer(text):
                    line_no = text[: match.start()].count("\n") + 1
                    offenders.append(f"{py.relative_to(ROOT)}:{line_no}")
    assert not offenders, (
        "发现 store.py 之外的 sqlite3 直连（违反宪章原则 III）：\n"
        + "\n".join(offenders)
    )


# ---- 004 T005：list_assets 读方法 ----

def _scene_asset(asset_id: str, name: str) -> dict:
    return {
        "asset_id": asset_id,
        "type": "scene",
        "name": name,
        "provenance": {
            "researched_at": "2026-10-20T00:00:00",
            "retriever": "test",
            "model": "test",
            "confidence": 0.5,
        },
    }


def test_list_assets_filters_by_type(tmp_path):
    from db.init_db import init as init_db
    from orchestrator.store import Store

    db = tmp_path / "t.db"
    init_db(db)
    store = Store(db)
    try:
        store.put_asset(_scene_asset("scene_a", "甲"))
        store.put_asset(_scene_asset("scene_b", "乙"))
        store.put_asset({**_scene_asset("prop_c", "丙"), "asset_id": "prop_c",
                        "type": "prop"})
        assert [a["name"] for a in store.list_assets("scene")] == ["甲", "乙"]
        assert len(store.list_assets()) == 3
        assert store.list_assets("epoch") == []
    finally:
        store.close()
