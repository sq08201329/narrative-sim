"""开发与 PyInstaller 冻结环境的统一路径边界。"""
import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent.parent


def default_home() -> Path:
    if not is_frozen():
        return resource_root()
    base = Path(os.environ.get("LOCALAPPDATA") or
                Path.home() / "AppData" / "Local")
    return base / "NarrativeSim"
