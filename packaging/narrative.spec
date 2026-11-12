from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

ROOT = Path.cwd().resolve()
datas = [
    (str(ROOT / "schemas"), "schemas"),
    (str(ROOT / "config.ini"), "."),
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "resources"), "resources"),
    (str(ROOT / "packages/worldseed/shared"), "shared"),
    (str(ROOT / "packages/worldseed/configs"), "configs"),
]
datas += collect_data_files("rfc3987_syntax")
datas += copy_metadata("gpt-researcher")
datas += copy_metadata("gptr-deepseek-retriever")
datas += copy_metadata("tiktoken")
hiddenimports = ["server", "utils", "tiktoken_ext.openai_public"]
for package in ("gpt_researcher", "worldseed", "tinytroupe", "selenium"):
    package_datas, _, package_hidden = collect_all(package)
    datas += package_datas
    hiddenimports += package_hidden
for name in ("gpt-researcher", "gptr-mcp", "worldseed"):
    datas.append((str(ROOT / "packages" / name / "LICENSE"), f"licenses/{name}"))

a = Analysis(
    [str(ROOT / "packaging/entrypoint.py")],
    pathex=[str(ROOT), str(ROOT / "packages/gptr-mcp")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="NarrativeSim", console=True,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    name="NarrativeSim",
)
