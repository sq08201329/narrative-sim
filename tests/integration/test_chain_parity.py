"""US2 链路同构：真链路复用最小链路的资产与流程，差异只在后端注入。

覆盖 spec：FR-005 / US2 AC1-AC2。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

REAL = (ROOT / "scripts" / "run_real_chain.py").read_text(encoding="utf-8")


def test_real_chain_reuses_assets_and_flow():
    """真链路不得重复定义资产字面量，必须复用 run_minimal_chain 的定义与流程。"""
    assert "from run_minimal_chain import" in REAL
    assert "run_simulation" in REAL and "export_jsonl" in REAL
    assert '"asset_id": "char_su_wanqing"' not in REAL, "真链路重复定义了资产"
    assert "MockPersonaBackend" not in REAL


def test_real_chain_differs_only_in_backend():
    assert "TinyTroupeBackend" in REAL, "真链路应注入 TinyTroupeBackend"


def test_mock_chain_works_without_any_keys(tmp_path):
    """无密钥环境：Mock 链路照常验收通过（US2 AC2）。"""
    env = {k: v for k, v in __import__("os").environ.items()
           if not k.startswith(("OPENAI_", "DEEPSEEK_", "MODEL_"))}
    proc = subprocess.run(
        [sys.executable, "scripts/run_minimal_chain.py",
         "--db", str(tmp_path / "s.db"), "--out", str(tmp_path / "o.jsonl"),
         "--run-id", "parity_run"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "验收通过" in proc.stdout
