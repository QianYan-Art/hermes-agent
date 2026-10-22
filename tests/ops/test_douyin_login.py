from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
import struct
import sys
from pathlib import Path

import pytest

SERVICE_PATH = Path(__file__).parents[2] / "ops" / "douyin-login" / "service.py"
SPEC = importlib.util.spec_from_file_location("douyin_login_service", SERVICE_PATH)
assert SPEC is not None and SPEC.loader is not None
douyin_login = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = douyin_login
SPEC.loader.exec_module(douyin_login)


def test_parse_request_accepts_only_the_two_single_field_actions():
    assert douyin_login.parse_request(b'{"action":"status"}\n') == "status"
    assert douyin_login.parse_request(b'{"action":"login"}') == "login"


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"not-json\n",
        b'{"action":"status","url":"https://example.com"}\n',
        b'{"action":"status","action":"login"}\n',
        b'{"action":"delete"}\n',
        b'{"action":1}\n',
        b'{"action":"status"}\n{}\n',
        b"\xff\n",
    ],
)
def test_parse_request_rejects_malformed_or_expanded_protocol(payload: bytes):
    with pytest.raises(douyin_login.ProtocolError):
        douyin_login.parse_request(payload)


def test_parse_request_enforces_size_limit():
    with pytest.raises(douyin_login.ProtocolError, match="4096"):
        douyin_login.parse_request(b" " * (douyin_login.MAX_REQUEST_BYTES + 1))


def test_login_overlay_overrides_stale_authenticated_background():
    snapshot = {"has_creator_navigation": True, "expected_account_visible": True, "qr_visible": True}
    assert douyin_login.classify_page(snapshot, "creator-id") == "login_required"


def test_notify_ready_targets_real_process_and_removes_child_environment(monkeypatch):
    captured = {}

    class Notifier:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, seconds):
            assert seconds == 2

        def connect(self, address):
            captured["address"] = address

        def sendall(self, payload):
            captured["payload"] = payload

    monkeypatch.setenv("NOTIFY_SOCKET", "@test-notify")
    monkeypatch.setattr(douyin_login.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(douyin_login.socket, "socket", lambda *args: Notifier())
    douyin_login.notify_systemd_ready()
    assert captured["address"] == "\0test-notify"
    assert b"MAINPID=" in captured["payload"]
    assert b"NOTIFYACCESS=main" in captured["payload"]
    assert b"READY=1" in captured["payload"]
    assert "NOTIFY_SOCKET" not in douyin_login.os.environ


@pytest.mark.parametrize("outcome", ["exited", "timeout", "wrong_command", "wrong_owner", "zombie", "signal_race"])
def test_stop_service_checks_target_and_waits_for_exit(tmp_path, monkeypatch, outcome):
    pid = 123456
    process = tmp_path / str(pid)
    process.mkdir()
    command = [sys.executable, str(SERVICE_PATH.resolve())]
    if outcome in {"wrong_command", "zombie"}:
        command[1] = "other-service.py"
    (process / "cmdline").write_bytes(b"\0".join(map(douyin_login.os.fsencode, command)))
    monkeypatch.setattr(douyin_login.os, "getuid", lambda: process.stat().st_uid + (outcome == "wrong_owner"), raising=False)
    monkeypatch.setattr(douyin_login.os, "pidfd_open", lambda target: 99 if target == pid else None, raising=False)
    sent, closed = [], []
    def send_signal(*args):
        sent.append(args)
        if outcome == "signal_race":
            raise ProcessLookupError

    monkeypatch.setattr(douyin_login.signal, "pidfd_send_signal", send_signal, raising=False)
    monkeypatch.setattr(douyin_login.os, "close", closed.append)

    def wait(readers, writers, errors, timeout):
        if timeout == 0:
            return ([99] if outcome == "zombie" else [], [], [])
        assert (readers, writers, errors, timeout) == ([99], [], [], 40)
        return ([] if outcome == "timeout" else [99], [], [])

    monkeypatch.setattr(douyin_login.select, "select", wait)
    if outcome in {"wrong_command", "wrong_owner"}:
        with pytest.raises(douyin_login.ConfigError):
            douyin_login.stop_service(pid, proc_root=tmp_path)
        assert sent == []
    elif outcome == "timeout":
        with pytest.raises(TimeoutError):
            douyin_login.stop_service(pid, proc_root=tmp_path)
    else:
        douyin_login.stop_service(pid, proc_root=tmp_path)
    assert closed == [99]
    if outcome in {"exited", "timeout"}:
        assert sent == [(99, douyin_login.signal.SIGTERM)]


def test_stop_service_accepts_an_already_exited_target(monkeypatch):
    def missing(pid):
        raise ProcessLookupError

    monkeypatch.setattr(douyin_login.os, "pidfd_open", missing, raising=False)
    douyin_login.stop_service(123456)
    with pytest.raises(douyin_login.ConfigError):
        douyin_login.stop_service(1)


def test_systemd_stop_uses_synchronous_helper():
    unit = (SERVICE_PATH.parent / "hermes-douyin.service").read_text(encoding="utf-8")
    assert "ExecStop=/opt/hermes-douyin/venv/bin/python /opt/hermes-douyin/service.py --stop $MAINPID" in unit


def test_config_requires_uid_and_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(douyin_login.socket, "SO_PEERCRED", 17, raising=False)
    data_dir = tmp_path / "state"
    socket_path = tmp_path / "run" / "douyin.sock"
    base = {
        "DOUYIN_DATA_DIR": str(data_dir),
        "DOUYIN_SOCKET_PATH": str(socket_path),
        "DOUYIN_EXPECTED_ACCOUNT": "creator-id",
        "DOUYIN_ALLOWED_UID": "1001",
    }
    config = douyin_login.ServiceConfig.from_env(base)
    assert config.allowed_uid == 1001
    assert config.profile_dir == data_dir / "chromium-profile"

    missing_uid = dict(base)
    del missing_uid["DOUYIN_ALLOWED_UID"]
    with pytest.raises(douyin_login.ConfigError):
        douyin_login.ServiceConfig.from_env(missing_uid)

    relative_path = dict(base, DOUYIN_SOCKET_PATH="socket")
    with pytest.raises(douyin_login.ConfigError):
        douyin_login.ServiceConfig.from_env(relative_path)


class FakePeerSocket:
    def __init__(self, uid: int):
        self.credentials = struct.pack("3i", 4321, uid, 100)

    def getsockopt(self, level: int, option: int, length: int) -> bytes:
        assert level == socket.SOL_SOCKET
        assert option == socket.SO_PEERCRED
        assert length == struct.calcsize("3i")
        return self.credentials


def test_peer_uid_uses_kernel_peer_credentials(monkeypatch):
    monkeypatch.setattr(douyin_login.socket, "SO_PEERCRED", 17, raising=False)
    assert douyin_login.peer_uid(FakePeerSocket(1001)) == 1001
    assert douyin_login.is_peer_authorized(FakePeerSocket(1001), 1001)
    assert not douyin_login.is_peer_authorized(FakePeerSocket(1002), 1001)


@pytest.mark.parametrize(
    ("snapshot", "expected_state"),
    [
        (
            {
                "has_creator_navigation": True,
                "expected_account_visible": True,
                "account_ids": [],
            },
            "logged_in",
        ),
        (
            {
                "has_creator_navigation": True,
                "expected_account_visible": False,
                "account_ids": [],
            },
            "unknown",
        ),
        (
            {
                "has_creator_navigation": True,
                "expected_account_visible": False,
                "account_ids": ["other-id"],
            },
            "account_mismatch",
        ),
        (
            {
                "has_creator_navigation": False,
                "verification_required": False,
                "login_control_visible": True,
            },
            "login_required",
        ),
        (
            {
                "has_creator_navigation": False,
                "verification_required": True,
                "login_control_visible": False,
            },
            "verification_required",
        ),
        (
            {
                "has_creator_navigation": True,
                "expected_account_visible": True,
                "page_error": True,
            },
            "page_error",
        ),
    ],
)
def test_classify_page_requires_account_and_creator_navigation(snapshot, expected_state):
    assert douyin_login.classify_page(snapshot, "creator-id") == expected_state


def test_verification_tab_label_alone_does_not_mean_a_challenge():
    snapshot = {
        "has_creator_navigation": False,
        "verification_required": False,
        "login_control_visible": False,
        "login_prompt_visible": False,
        "qr_visible": False,
    }
    assert douyin_login.classify_page(snapshot, "creator-id") == "unknown"


def test_response_limits_qr_image_and_uses_only_contract_fields():
    too_large = b"x" * (douyin_login.MAX_QR_BYTES + 1)
    result = douyin_login.make_response("login_required", qr_png=too_large)
    assert set(result) == {"ok", "state", "message"}
    assert result["ok"] is True

    result = douyin_login.make_response("login_required", qr_png=b"png")
    assert set(result) == {"ok", "state", "message", "qr_png_base64"}
    assert result["qr_png_base64"] == "cG5n"


class ConcurrentBrowser:
    def __init__(self):
        self.active = 0
        self.peak_active = 0

    async def handle(self, action: str):
        self.active += 1
        self.peak_active = max(self.peak_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return douyin_login.make_response("unknown")


class FailingBrowser:
    def __init__(self, error: Exception):
        self.error = error

    async def handle(self, action: str):
        raise self.error


@pytest.mark.asyncio
async def test_browser_operations_are_serialized():
    browser = ConcurrentBrowser()
    service = douyin_login.LoginService(browser)
    await asyncio.gather(service.process("status"), service.process("login"))
    assert browser.peak_active == 1


@pytest.mark.asyncio
async def test_timeout_and_browser_errors_are_safe_responses(caplog):
    slow = ConcurrentBrowser()
    service = douyin_login.LoginService(slow, operation_timeout=0.001)
    timed_out = await service.process("status")
    assert timed_out["state"] == "page_error"

    service = douyin_login.LoginService(
        FailingBrowser(RuntimeError("private page content and token"))
    )
    failed = await service.process("status")
    assert failed["state"] == "page_error"
    assert "private page content and token" not in caplog.text

    unavailable = await douyin_login.LoginService(
        FailingBrowser(douyin_login.BrowserUnavailable())
    ).process("login")
    assert unavailable == {
        "ok": False,
        "state": "unavailable",
        "message": "抖音登录服务暂时不可用。",
    }
