"""pytest 全局配置：把仓库根目录加入 sys.path（application 布局）。

另：TinyTroupe 在**包 import 瞬间**就按 cwd 建日志文件——conftest 先于
一切测试模块加载，在此整体换绑到 logs/（orchestrator/ttlog.py）。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orchestrator.ttlog import redirect_tinytroupe_log  # noqa: E402

redirect_tinytroupe_log(ROOT)
