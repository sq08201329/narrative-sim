import json

from db.init_db import init as init_db
from orchestrator import cli
from orchestrator.store import Store
from scripts.run_minimal_chain import CHARACTER, SCENE


def test_offline_cli_world_run_export(tmp_path, monkeypatch, capsys):
    home = tmp_path / "中文 路径"
    db = home / "data" / "cli.db"
    init_db(str(db))
    store = Store(str(db))
    store.put_asset(CHARACTER)
    store.put_asset(SCENE)
    store.close()
    monkeypatch.setenv("NARRATIVE_HOME", str(home))
    monkeypatch.setenv("NARRATIVE_DB", str(db))

    assert cli.main(["world", "create", "world_cli", "--characters",
                     CHARACTER["asset_id"], "--location", SCENE["asset_id"]]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["world_id"] == "world_cli"
    assert created["revision_pins"]

    assert cli.main(["run", "world_cli", "--run-id", "run_cli", "--ticks", "4",
                     "--backend", "mock"]) == 0
    run = json.loads(capsys.readouterr().out)
    assert run["event_count"] == 5
    assert run["cost_tokens"] is None

    out = home / "exports" / "run.jsonl"
    assert cli.main(["export", "run_cli", "--out", str(out)]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported == {"path": str(out), "count": 5}
    assert len(out.read_text(encoding="utf-8").splitlines()) == 5


def test_export_missing_run_has_no_success_artifact(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NARRATIVE_HOME", str(tmp_path))
    monkeypatch.setenv("NARRATIVE_DB", str(tmp_path / "cli.db"))
    out = tmp_path / "missing.jsonl"
    assert cli.main(["export", "missing", "--out", str(out)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "RunNotFound" in captured.err
    assert not out.exists()
