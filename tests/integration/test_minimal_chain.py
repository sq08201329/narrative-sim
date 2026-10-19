"""US1 集成测试：最小仿真链路（先写测试，确认 FAIL 后实现脚本）。

覆盖 spec：FR-008 全链路 / FR-010 离线 / SC-002 确定性 / SC-003 全量契约校验。
"""
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent.parent
EVENT_SCHEMA = json.loads(
    (ROOT / "schemas" / "event.schema.json").read_text(encoding="utf-8")
)


def _run_chain(db: Path, out: Path, run_id: str = "it_run") -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "scripts/run_minimal_chain.py",
            "--db", str(db), "--out", str(out), "--run-id", run_id,
        ],
        cwd=ROOT, capture_output=True, text=True,
    )


def _load_events(out: Path) -> list[dict]:
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]


def test_minimal_chain_acceptance(tmp_path):
    db, out = tmp_path / "sim.db", tmp_path / "events.jsonl"
    proc = _run_chain(db, out)

    assert proc.returncode == 0, proc.stderr
    assert "验收通过" in proc.stdout
    assert out.exists()

    events = _load_events(out)
    assert len(events) >= 5
    for ev in events:
        jsonschema.validate(ev, EVENT_SCHEMA)

    # 排序键单调不减；事件只引用 asset_id
    keys = [(e["tick"], e["seq"]) for e in events]
    assert keys == sorted(keys)
    assert all(e["characters"] for e in events)


def test_minimal_chain_deterministic(tmp_path):
    first = _run_chain(tmp_path / "a.db", tmp_path / "a.jsonl", "det_a")
    assert first.returncode == 0, first.stderr
    second = _run_chain(tmp_path / "b.db", tmp_path / "b.jsonl", "det_b")
    assert second.returncode == 0, second.stderr

    def normalize(events):
        return [{k: v for k, v in e.items() if k not in ("created_at", "run_id")}
                for e in events]

    assert normalize(_load_events(tmp_path / "a.jsonl")) == normalize(
        _load_events(tmp_path / "b.jsonl")
    )


def test_minimal_chain_rerun_same_db(tmp_path):
    """数据库已存在时重跑：建表幂等 + 显式 reset，仍完成验收。"""
    db, out = tmp_path / "sim.db", tmp_path / "events.jsonl"
    assert _run_chain(db, out).returncode == 0
    proc = _run_chain(db, out)
    assert proc.returncode == 0, proc.stderr
    assert "验收通过" in proc.stdout
