"""US3 成本记账：token 用量按 run_id 落库；Mock 不记假账。

覆盖 spec：FR-007 / SC-004；宪章原则 VI。
"""
import pytest

from db.init_db import init as init_db
from orchestrator.store import Store


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "cost.db"
    init_db(str(db))
    s = Store(str(db))
    yield s
    s.close()


def test_update_run_cost_persists(store):
    store.create_run("cost_run", "world_cost")
    store.update_run_cost("cost_run", 1234)
    row = store._conn.execute(
        "SELECT token_cost FROM runs WHERE run_id='cost_run'"
    ).fetchone()
    assert row["token_cost"] == 1234


def test_update_run_cost_unknown_run_raises(store):
    with pytest.raises(KeyError, match="运行不存在"):
        store.update_run_cost("ghost_run", 100)


def test_mock_chain_leaves_cost_zero(tmp_path):
    """Mock 链路不调 LLM，token_cost 必须保持 0（SC-004）。"""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    db = tmp_path / "mock.db"
    proc = subprocess.run(
        [sys.executable, "scripts/run_minimal_chain.py",
         "--db", str(db), "--out", str(tmp_path / "o.jsonl"),
         "--run-id", "mock_cost_run"],
        cwd=root, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr

    s = Store(str(db))
    try:
        row = s._conn.execute(
            "SELECT token_cost FROM runs WHERE run_id='mock_cost_run'"
        ).fetchone()
        assert row["token_cost"] == 0
    finally:
        s.close()
