"""TinyTroupe 日志路径重定向（数据文件管理）。

TinyTroupe 在包 import 时就 start_logger，按 cwd 建 tinytroupe.<ts>.log——
无法通过"先 import 再设全局"抢占（import 副作用已完成）。本模块在 import
后整体换绑 file handler 到 <root>/logs/，并清理 cwd 下刚建的空壳文件。

幂等：handler 已在 logs/ 下则跳过。被 tests/conftest.py（测试）与
persona_tinytroupe.__init__（真机）共用。
"""
import logging
from datetime import datetime
from pathlib import Path


def redirect_tinytroupe_log(root: Path) -> None:
    try:
        import tinytroupe.utils.config as cfg
    except ImportError:
        return
    try:
        log_dir = root / "logs"
        log_dir.mkdir(exist_ok=True)
        current = cfg._log_file_path
        if current and str(current).startswith(str(log_dir)):
            return  # 已就位
        new_path = log_dir / f"tinytroupe.{datetime.now():%Y%m%d_%H%M%S}.log"

        root_logger = logging.getLogger()
        old = cfg._file_handler
        if old is not None:
            root_logger.removeHandler(old)
            try:
                old.close()
            except Exception:
                pass
        cfg._log_file_path = new_path
        cfg._file_handler = cfg._create_file_handler()
        root_logger.addHandler(cfg._file_handler)

        # 清理 import 副作用在 cwd 建的空壳
        if current:
            old_path = Path(current)
            try:
                if (old_path.exists()
                        and old_path.stat().st_size < 512
                        and old_path.parent != log_dir):
                    old_path.unlink()
            except OSError:
                pass
    except Exception:
        pass  # 日志重定向失败永不阻塞主流程
