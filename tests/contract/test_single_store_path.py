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
