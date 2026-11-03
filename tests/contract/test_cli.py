import json

import pytest

from orchestrator import cli, workflows


def test_help_lists_core_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for command in ("research", "world", "run", "export", "mcp", "start"):
        assert command in out


def test_argument_error_returns_two():
    with pytest.raises(SystemExit) as exc:
        cli.main(["research", "q", "--type", "weapon"])
    assert exc.value.code == 2


def test_research_uses_library_db_not_project_db(tmp_path, monkeypatch, capsys):
    seen = []

    def fake_research(db_path, query, asset_type):
        seen.append(db_path)
        return {"asset_id": "scene_1", "deduplicated": False}

    monkeypatch.setattr(workflows, "research", fake_research)
    monkeypatch.delenv("LIBRARY_DB", raising=False)
    project_db = tmp_path / "project.db"
    base = ["--home", str(tmp_path), "--db", str(project_db),
            "research", "酒楼", "--type", "scene"]
    assert cli.main(base) == 0
    assert json.loads(capsys.readouterr().out)["asset_id"] == "scene_1"

    library_db = tmp_path / "custom-library.db"
    assert cli.main(["--library-db", str(library_db), *base]) == 0
    capsys.readouterr()
    assert seen == [str(tmp_path / "data" / "library.db"), str(library_db)]
    assert project_db.exists() is False


def test_world_run_and_export_options(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(workflows, "create_world",
                        lambda *args, **kwargs: calls.append(("create", args, kwargs)) or
                        {"world_id": "w1", "revision_pins": {"char_a": 0}})
    monkeypatch.setattr(workflows, "run_simulation",
                        lambda *args, **kwargs: calls.append(("run", args, kwargs)) or
                        {"run_id": "r1", "event_count": 5, "ticks": 4,
                         "cost_tokens": None})
    monkeypatch.setattr(workflows, "export_events",
                        lambda *args: calls.append(("export", args)) or
                        {"path": "events.jsonl", "count": 5})
    base = ["--home", str(tmp_path), "--db", str(tmp_path / "cli.db")]
    assert cli.main([*base, "world", "create", "w1", "--characters", "char_a,char_b",
                     "--location", "scene_x", "--memory-from", "r0"]) == 0
    assert cli.main([*base, "run", "w1", "--run-id", "r1", "--ticks", "4",
                     "--backend", "mock", "--resume", "--dm"]) == 0
    assert cli.main([*base, "export", "r1", "--out", "events.jsonl"]) == 0
    assert calls[0][1][2] == ["char_a", "char_b"]
    assert calls[0][2]["memory_from"] == "r0"
    assert calls[1][2]["backend"] == "mock"
    assert calls[1][2]["resume"] is True
    assert calls[1][2]["dm"] is True
    assert calls[2][1][-1] == "events.jsonl"


def test_business_failure_is_readable_without_traceback(tmp_path, monkeypatch, capsys):
    def fail(*args):
        raise RuntimeError("run r 不存在")
    monkeypatch.setattr(workflows, "export_events", fail)
    code = cli.main(["--home", str(tmp_path), "export", "r", "--out", "x.jsonl"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "run r 不存在" in captured.err
    assert "Traceback" not in captured.err
