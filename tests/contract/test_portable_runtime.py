from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parent.parent.parent


def test_workspace_has_no_legacy_absolute_paths():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    services = (ROOT / "orchestrator" / "services.py").read_text(encoding="utf-8")
    starter = (ROOT / "scripts" / "start_stack.ps1").read_text(encoding="utf-8")
    for text in (pyproject, services, starter):
        assert "D:/kimicode_repos" not in text
        assert r"D:\kimicode_repos" not in text
        assert r"D:\gh_projects" not in text
    config = tomllib.loads(pyproject)
    for name in ("worldseed", "gptr-mcp", "gpt-researcher", "gptr-deepseek-retriever"):
        assert config["tool"]["uv"]["sources"][name]["workspace"] is True


def test_vendored_components_have_resources_and_provenance():
    for name in ("worldseed", "gptr-mcp", "gpt-researcher"):
        package = ROOT / "packages" / name
        assert (package / "LICENSE").is_file()
        assert (package / "UPSTREAM.md").is_file()
    assert (ROOT / "packages/worldseed/shared/languages.json").is_file()
    assert (ROOT / "packages/worldseed/configs").is_dir()
    assert (ROOT / "packages/worldseed/src/worldseed/models/config_schema.py").is_file()
    prompt = (ROOT / "packages/worldseed/src/worldseed/dm/prompt.py").read_text(encoding="utf-8")
    assert 'read_text(encoding="utf-8")' in prompt
