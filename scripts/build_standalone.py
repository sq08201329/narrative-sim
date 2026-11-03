"""构建 Windows 免安装目录与 ZIP；不读取用户配置或数据库。"""
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "NarrativeSim"
ARCHIVE = DIST / "NarrativeSim-windows-x64.zip"


def main() -> int:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "packaging/narrative.spec"],
        cwd=ROOT, check=True)
    (APP / "README.md").write_text((ROOT / "README.md").read_text(encoding="utf-8"),
                                  encoding="utf-8")
    shutil.copyfile(ROOT / ".env.example", APP / ".env.example")
    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    info = {
        "name": "narrative-sim", "version": version,
        "pyinstaller": importlib.metadata.version("pyinstaller"),
        "target": "windows-x64",
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (APP / "BUILD-INFO.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in APP.rglob("*"):
            if path.is_file():
                bundle.write(path, Path(APP.name) / path.relative_to(APP))
    print(f"应用目录: {APP}")
    print(f"免安装包: {ARCHIVE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
