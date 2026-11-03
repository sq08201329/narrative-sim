from pathlib import Path

import pytest

from orchestrator import init_app


def test_initialize_creates_templates_and_skill(tmp_path):
    result = init_app.initialize(tmp_path)
    assert result["home"] == str(tmp_path)
    assert all(item["status"] == "created" for item in result["directories"])
    assert all(item["status"] == "created" for item in result["files"])
    assert (tmp_path / "config.ini").is_file()
    assert (tmp_path / ".env").is_file()
    skill = tmp_path / "skills/narrative-sim/SKILL.md"
    assert skill.read_bytes() == init_app.SKILL_SOURCE.read_bytes()
    assert not list(tmp_path.rglob("*.db"))


def test_initialize_preserves_existing_and_fills_missing(tmp_path):
    init_app.initialize(tmp_path)
    custom = {
        "config.ini": b"custom-config",
        ".env": b"custom-env",
        "skills/narrative-sim/SKILL.md": b"custom-skill",
    }
    for name, content in custom.items():
        (tmp_path / name).write_bytes(content)
    removed = tmp_path / "models"
    removed.rmdir()
    result = init_app.initialize(tmp_path)
    for name, content in custom.items():
        assert (tmp_path / name).read_bytes() == content
    assert all(item["status"] == "existing" for item in result["files"])
    assert next(item for item in result["directories"]
                if item["path"].endswith("models"))["status"] == "created"


def test_missing_template_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(init_app, "TEMPLATES",
                        [(Path("config.ini"), tmp_path / "empty" / "config.ini")])
    with pytest.raises(init_app.InitError, match="模板"):
        init_app.initialize(tmp_path / "home")
