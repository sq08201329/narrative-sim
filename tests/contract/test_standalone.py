import sys
from pathlib import Path

from orchestrator import cli, init_app, runtime, services


def test_frozen_resource_root_and_user_home(tmp_path, monkeypatch):
    frozen_root = tmp_path / "frozen-resources"
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.sys, "_MEIPASS", str(frozen_root), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert runtime.resource_root() == frozen_root
    assert runtime.default_home() == tmp_path / "local" / "NarrativeSim"


def test_development_home_remains_repository_root(monkeypatch):
    monkeypatch.delattr(runtime.sys, "frozen", raising=False)
    assert runtime.default_home() == runtime.resource_root()


def test_user_config_is_copied_only_once(tmp_path, monkeypatch):
    source = tmp_path / "config.ini"
    source.write_text("default", encoding="utf-8")
    monkeypatch.setattr(init_app, "TEMPLATES", [(Path("config.ini"), source)])
    home = tmp_path / "home"
    cli._prepare_user_home(home)
    config = home / "config.ini"
    assert config.read_text(encoding="utf-8") == "default"
    config.write_text("custom", encoding="utf-8")
    cli._prepare_user_home(home)
    assert config.read_text(encoding="utf-8") == "custom"


def test_frozen_services_callback_same_executable(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://localhost:9379/v1")
    monkeypatch.setenv("GPTR_MCP_URL", "http://localhost:8000/mcp")
    monkeypatch.setattr(services, "is_frozen", lambda: True)
    monkeypatch.setattr(services.sys, "executable", r"C:\App\NarrativeSim.exe")
    specs = services._default_specs(tmp_path, tmp_path / "play.db")
    gptr = next(spec for spec in specs if spec.name == "gptr-mcp")
    narrative = next(spec for spec in specs if spec.name == "narrative-sim")
    assert gptr.command == [r"C:\App\NarrativeSim.exe", "_gptr"]
    assert narrative.command[0] == r"C:\App\NarrativeSim.exe"
    assert "python" not in narrative.command
    assert "uv" not in narrative.command
    assert "mcp" in narrative.command
    assert "-m" not in narrative.command
