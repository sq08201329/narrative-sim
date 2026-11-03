import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator import cli, services


def test_stale_record_is_not_owned(tmp_path):
    spec = services.ServiceSpec(
        name="test", command=["python", "test-marker"], cwd=tmp_path,
        port=65530, health_url="", marker="test-marker", ready_timeout=0.1)
    manager = services.StackManager(tmp_path, tmp_path / "test.db", [spec])
    manager._write_record(spec, 99999999, 1.0, spec.command)
    status = manager.status()[0]
    assert status["name"] == "test"
    assert status["state"] == "stopped"
    assert status["managed"] is False


def test_status_reports_unavailable_with_exit_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(services, "service_action", lambda *args: {
        "action": "status", "database": str(tmp_path / "db"),
        "ready": False,
        "services": [{"name": "embedding", "state": "stopped", "managed": False}],
    })
    assert cli.main(["--home", str(tmp_path), "status"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ready"] is False
    assert result["services"][0]["state"] == "stopped"


def test_start_failure_has_no_success_json(tmp_path, monkeypatch, capsys):
    def fail(*args):
        raise services.ServiceError("端口被外部进程占用")
    monkeypatch.setattr(services, "service_action", fail)
    assert cli.main(["--home", str(tmp_path), "start"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "端口被外部进程占用" in captured.err


def test_gptr_uses_workspace_and_root_python(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://localhost:9379/v1")
    monkeypatch.setenv("GPTR_MCP_URL", "http://localhost:8000/mcp")
    specs = services._default_specs(tmp_path, tmp_path / "play.db")
    gptr = next(spec for spec in specs if spec.name == "gptr-mcp")
    assert gptr.command[0] == sys.executable
    assert Path(gptr.command[1]) == services.ROOT / "packages" / "gptr-mcp" / "server.py"
    assert ".venv" not in gptr.command[1]


def test_missing_model_file_names_config(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://localhost:9379/v1")
    monkeypatch.setenv("LITERT_LM", "fake-litert")
    monkeypatch.setenv("EMBEDDING_MODEL_FILE", str(tmp_path / "missing.litertlm"))
    monkeypatch.setattr(services, "_http_ready", lambda url: False)
    monkeypatch.setattr(services.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="", stderr=""))
    with pytest.raises(services.ServiceError, match="EMBEDDING_MODEL_FILE"):
        services._prepare_embedding()


def test_existing_model_is_imported_from_configured_file(tmp_path, monkeypatch):
    model = tmp_path / "model.litertlm"
    model.write_bytes(b"test")
    calls = []
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://localhost:9379/v1")
    monkeypatch.setenv("LITERT_LM", "fake-litert")
    monkeypatch.setenv("EMBEDDING_MODEL_FILE", str(model))
    monkeypatch.setenv("EMBEDDING_MODEL", "test-model")
    monkeypatch.setattr(services, "_http_ready", lambda url: False)

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(services.subprocess, "run", fake_run)
    services._prepare_embedding()
    assert calls[1] == ["fake-litert", "import", str(model), "test-model"]
