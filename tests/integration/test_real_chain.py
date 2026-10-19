"""US1/US3 在线验收：真后端链路端到端（需真实密钥，无密钥自动 skip）。

覆盖 spec：FR-008 / SC-001 / SC-004。打标 real，不进离线回归路径。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
EVENT_SCHEMA = json.loads(
    (ROOT / "schemas" / "event.schema.json").read_text(encoding="utf-8")
)

pytestmark = pytest.mark.real

HAS_KEY = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"))


@pytest.mark.skipif(not HAS_KEY, reason="无 LLM 密钥，跳过在线验收")
def test_real_chain_end_to_end(tmp_path):
    db, out = tmp_path / "real.db", tmp_path / "real.jsonl"
    proc = subprocess.run(
        [sys.executable, "scripts/run_real_chain.py",
         "--db", str(db), "--out", str(out), "--run-id", "real_it_run"],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, proc.stderr
    assert "验收通过" in proc.stdout

    events = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(events) >= 5
    for ev in events:
        jsonschema.validate(ev, EVENT_SCHEMA)

    sys.path.insert(0, str(ROOT))
    from orchestrator.store import Store

    store = Store(str(db))
    try:
        row = store._conn.execute(
            "SELECT token_cost, status FROM runs WHERE run_id='real_it_run'"
        ).fetchone()
        assert row["status"] == "done"
        assert row["token_cost"] > 0, "真后端运行必须记录非零 token 成本"
    finally:
        store.close()
