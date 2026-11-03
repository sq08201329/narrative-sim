"""用户目录与只读模板的非破坏性初始化。"""
import shutil
from pathlib import Path

from .runtime import resource_root

ROOT = resource_root()
SKILL_SOURCE = ROOT / "resources" / "skills" / "narrative-sim" / "SKILL.md"
DIRECTORIES = ("data", "logs", "run", "models", "cache", "skills")
TEMPLATES = (
    (Path("config.ini"), ROOT / "config.ini"),
    (Path(".env"), ROOT / ".env.example"),
    (Path("skills/narrative-sim/SKILL.md"), SKILL_SOURCE),
)


class InitError(RuntimeError):
    pass


def _created(path: Path) -> bool:
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def initialize(home: Path) -> dict:
    home = Path(home).resolve()
    directories = []
    files = []
    for name in DIRECTORIES:
        path = home / name
        directories.append({"path": str(path), "status": "created" if _created(path) else "existing"})
    for relative, source in TEMPLATES:
        target = home / relative
        if target.exists():
            files.append({"path": str(target), "status": "existing"})
            continue
        if not source.is_file():
            raise InitError(f"初始化模板不存在: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            raise InitError(f"无法写入初始化文件 {target}: {exc}") from exc
        files.append({"path": str(target), "status": "created"})
    return {"home": str(home), "directories": directories, "files": files}
