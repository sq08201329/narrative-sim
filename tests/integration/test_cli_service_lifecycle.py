import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from orchestrator.services import ServiceSpec, StackManager

ROOT = Path(__file__).resolve().parent.parent.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def spec_for(port, cwd, timeout=5):
    return ServiceSpec(
        name="test-http",
        command=[sys.executable, "-m", "http.server", str(port),
                 "--bind", "127.0.0.1"],
        cwd=cwd, port=port,
        health_url=f"http://127.0.0.1:{port}/", marker="http.server",
        ready_timeout=timeout)


def test_managed_service_full_lifecycle(tmp_path):
    spec = spec_for(free_port(), tmp_path)
    manager = StackManager(tmp_path, tmp_path / "cli.db", [spec])
    try:
        started = manager.start()
        assert started[0]["state"] == "ready"
        first_pid = started[0]["pid"]
        assert manager.start()[0]["pid"] == first_pid
        assert manager.status()[0]["managed"] is True

        restarted = manager.restart()
        assert restarted[0]["state"] == "ready"
        assert restarted[0]["pid"] != first_pid
    finally:
        stopped = manager.stop()
    assert stopped[0]["state"] == "stopped"
    assert manager.stop()[0]["state"] == "stopped"


def test_external_service_is_reused_but_never_stopped(tmp_path):
    spec = spec_for(free_port(), tmp_path)
    log = open(tmp_path / "external.log", "wb")
    process = subprocess.Popen(spec.command, cwd=spec.cwd,
                               stdout=log, stderr=subprocess.STDOUT)
    manager = StackManager(tmp_path, tmp_path / "cli.db", [spec])
    try:
        deadline = time.monotonic() + 5
        while not manager._healthy(spec):
            if time.monotonic() > deadline:
                pytest.fail("外部测试服务未就绪")
            time.sleep(0.05)
        assert manager.status()[0]["state"] == "external"
        assert manager.start()[0]["state"] == "external"
        assert manager.stop()[0]["state"] == "external"
        assert psutil.pid_exists(process.pid)
    finally:
        process.terminate()
        process.wait(timeout=5)
        log.close()


def test_port_conflict_is_rejected_without_killing_external_process(tmp_path):
    spec = spec_for(free_port(), tmp_path)
    process = subprocess.Popen(spec.command, cwd=spec.cwd,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    other = ServiceSpec(name="other", command=spec.command, cwd=spec.cwd,
                        port=spec.port,
                        health_url=f"http://127.0.0.1:{spec.port}/not-ready",
                        marker="other-marker", ready_timeout=0.2)
    manager = StackManager(tmp_path, tmp_path / "cli.db", [other])
    try:
        deadline = time.monotonic() + 5
        while not manager._listener_pid(other):
            if time.monotonic() > deadline:
                pytest.fail("外部测试端口未监听")
            time.sleep(0.05)
        with pytest.raises(Exception, match="占用|未就绪"):
            manager.start()
        assert psutil.pid_exists(process.pid)
    finally:
        process.terminate()
        process.wait(timeout=5)
