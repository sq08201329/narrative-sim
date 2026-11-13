"""构建免安装目录与 ZIP；不读取用户配置或数据库。

跨平台：在 macOS 上产出 darwin 应用，在 Windows 上产出 windows-x64 应用。
PyInstaller 不支持交叉编译，需在目标平台上运行本脚本。
"""
import importlib.metadata
import json
import platform
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


def platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        system = "macos"
    if machine in ("x86_64", "amd64"):
        machine = "x64"
    elif machine in ("arm64", "aarch64"):
        machine = "arm64"
    return f"{system}-{machine}"


TAG = platform_tag()
ARCHIVE = DIST / f"NarrativeSim-{TAG}.zip"


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
        "target": TAG,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (APP / "BUILD-INFO.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # macOS：移除隔离属性，避免 Gatekeeper 拦截未签名可执行
    if platform.system().lower() == "darwin":
        subprocess.run(["xattr", "-cr", str(APP)], check=False)
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in APP.rglob("*"):
            if path.is_file():
                bundle.write(path, Path(APP.name) / path.relative_to(APP))
    print(f"应用目录: {APP}")
    print(f"免安装包: {ARCHIVE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
