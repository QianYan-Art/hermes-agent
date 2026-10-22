"""临时窗口的启动顺序与安全失败回归，不连接真实浏览器。"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("douyin_manual_test", Path(__file__).resolve().parents[2] / "ops/douyin-login/manual_window.py")
window = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(window)


def test_both_services_start_before_readiness_probe(monkeypatch):
    launched = []
    monkeypatch.setattr(window.subprocess, "run", lambda command, **kwargs: launched.append(command))
    monkeypatch.setattr(window, "listener_belongs_to_unit", lambda unit, port: True)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    probed = []

    def connect(address, **kwargs):
        assert len(launched) == 2
        assert address[0] == "127.0.0.1"
        probed.append(address[1])
        return Connection()

    monkeypatch.setattr(window.socket, "create_connection", connect)
    window.start_units("123", ":99", "/tmp/private-auth")
    assert probed == [5905, 6085]
    assert "-no6" in launched[0]
    assert "-permitfiletransfer" not in launched[0]
    assert all("--property=RuntimeMaxSec=15min" in command for command in launched)


@pytest.mark.parametrize("state,group,inode,expected", [
    ("active", "/system.slice/hermes-douyin-manual-vnc.service", "12345", True),
    ("inactive", "/system.slice/hermes-douyin-manual-vnc.service", "12345", False),
    ("active", "/system.slice/unrelated.service", "12345", False),
    ("active", "/system.slice/hermes-douyin-manual-vnc.service", "99999", False),
])
def test_listener_must_belong_to_the_active_unit(monkeypatch, tmp_path, state, group, inode, expected):
    unit = window.UNITS[1]
    monkeypatch.setattr(window.subprocess, "check_output", lambda *args, **kwargs: f"ActiveState={state}\nControlGroup={group}\n")
    proc = tmp_path / "proc"
    (proc / "net").mkdir(parents=True)
    (proc / "net/tcp").write_text("header\n0: 0100007F:1711 00000000:0000 0A 0:0 0:0 0 999 0 12345\n")
    descriptors = proc / "42/fd"
    descriptors.mkdir(parents=True)
    (descriptors / "8").touch()
    cgroups = tmp_path / "cgroups"
    group_path = cgroups / "system.slice" / unit
    group_path.mkdir(parents=True)
    (group_path / "cgroup.procs").write_text("42\n")
    monkeypatch.setattr(window.os, "readlink", lambda path: f"socket:[{inode}]")
    assert window.listener_belongs_to_unit(unit, 5905, proc_root=proc, cgroup_root=cgroups) is expected


def test_occupied_port_from_unrelated_service_does_not_report_ready(monkeypatch):
    monkeypatch.setattr(window.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "listener_belongs_to_unit", lambda unit, port: False)
    clock = iter([0, 6])
    monkeypatch.setattr(window.time, "monotonic", lambda: next(clock))

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(window.socket, "create_connection", lambda *args, **kwargs: Connection())
    with pytest.raises(RuntimeError, match="端口不属于本次服务"):
        window.start_units("123", ":99", "/tmp/private-auth")


def test_failed_web_service_does_not_report_ready(monkeypatch):
    def fail(command, **kwargs):
        if "--unit=hermes-douyin-manual-web" in command:
            raise window.subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(window.subprocess, "run", fail)
    with pytest.raises(window.subprocess.CalledProcessError):
        window.start_units("123", ":99", "/tmp/private-auth")


def test_close_refuses_to_claim_success_while_active(monkeypatch, tmp_path):
    monkeypatch.setattr(window.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(window.subprocess, "check_output", lambda *args, **kwargs: "active\n")
    monkeypatch.setattr(window, "PASSWORD_FILE", tmp_path / "unused.pass")
    with pytest.raises(RuntimeError, match="未完全停止"):
        window.close_window()
