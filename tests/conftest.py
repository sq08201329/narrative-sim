"""pytest 全局配置：把仓库根目录加入 sys.path（application 布局）。

另：TinyTroupe 在**包 import 瞬间**就按 cwd 建日志文件——conftest 先于
一切测试模块加载，在此整体换绑到 logs/（orchestrator/ttlog.py）。

测试环境隔离（B 方案，只动测试基础设施，不改产品代码）：
项目根有真实 `.env`，其中 load_dotenv 会在两处把变量回填进 os.environ——
模块 import 期（orchestrator/llm.py、orchestrator/images.py）和后端构造期
（TinyTroupeBackend.__init__）。回填会让「未配置嵌入」这类场景无法复现，
所以除 real 标记的在线用例，单测一律不读项目 .env。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orchestrator.ttlog import redirect_tinytroupe_log  # noqa: E402

redirect_tinytroupe_log(ROOT)

# .env 会注入的外部键：单测里一律清掉，保证「缺失/未配置」场景可复现
_DOTENV_INJECTED_KEYS = (
    "EMBEDDING_API_BASE",
    "EMBEDDING_MODEL",
    "EMBEDDING_TIMEOUT_S",
    "EMBEDDING_MAX_CHARS",
)

# 已绑定 load_dotenv 的模块（`from dotenv import load_dotenv` 是值拷贝，
# 只 patch dotenv.load_dotenv 管不到已 import 的模块，必须逐个换绑）
_LOAD_DOTENV_MODULES = (
    "orchestrator.persona_tinytroupe",
    "orchestrator.llm",
    "orchestrator.images",
)


@pytest.fixture(autouse=True)
def isolate_project_env(monkeypatch, request):
    """单测默认不读项目 .env；标了 real 的在线用例除外（需要真实密钥）。"""
    if request.node.get_closest_marker("real"):
        return

    import dotenv

    def _no_dotenv(*args, **kwargs):
        return False

    # 1) 阻止后端构造期再次回填 .env
    monkeypatch.setattr(dotenv, "load_dotenv", _no_dotenv)
    for name in _LOAD_DOTENV_MODULES:
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "load_dotenv"):
            monkeypatch.setattr(module, "load_dotenv", _no_dotenv)

    # 2) 清掉 import 期已回填的嵌入相关键（.env 里有值，会干扰降级场景）
    for key in _DOTENV_INJECTED_KEYS:
        monkeypatch.delenv(key, raising=False)
