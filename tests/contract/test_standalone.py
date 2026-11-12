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


def test_packaging_spec_collects_frozen_runtime_dependencies():
    spec = (Path(__file__).resolve().parent.parent.parent /
            "packaging" / "narrative.spec").read_text(encoding="utf-8")
    assert '"selenium"' in spec
    assert '"tiktoken_ext.openai_public"' in spec
    assert 'copy_metadata("tiktoken")' in spec
    assert 'collect_data_files("litellm")' in spec


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


def test_dm_prompt_loads_languages_in_source_tree():
    """源码树形态：languages.json 按包根 shared 解析（回归锚点）。"""
    from worldseed.dm import prompt as dm_prompt
    names = dm_prompt._load_lang_names()
    assert isinstance(names, dict) and names


def test_dm_prompt_loads_languages_frozen(tmp_path, monkeypatch):
    """冻结形态：languages.json 从 _MEIPASS/shared 解析，不再指到 bundle 根。"""
    from worldseed.dm import prompt as dm_prompt
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "languages.json").write_text('{"zh": "中文"}', encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert dm_prompt._load_lang_names() == {"zh": "中文"}


def test_dm_prompt_languages_error_lists_candidates(tmp_path, monkeypatch):
    """全部候选路径缺失时，报错信息列出尝试过的路径。"""
    import worldseed.dm.prompt as dm_prompt
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "nope"), raising=False)
    monkeypatch.setattr(dm_prompt, "__file__", str(tmp_path / "a/b/c/d/prompt.py"))
    try:
        dm_prompt._load_lang_names()
    except FileNotFoundError as e:
        assert "nope" in str(e) and "尝试" in str(e)
    else:
        raise AssertionError("应抛 FileNotFoundError")
