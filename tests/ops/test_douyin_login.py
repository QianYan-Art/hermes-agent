from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import socket
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


def test_auto_recovery_protocol_is_explicit_and_cannot_expand_actions():
    assert douyin_login.parse_request(b'{"action":"login","recover":true}') == "recover_login"
    for payload in [b'{"action":"login","recover":false}', b'{"action":"login","recover":1}',
                    b'{"action":"status","recover":true}', b'{"action":"recover_login"}']:
        with pytest.raises(douyin_login.ProtocolError):
            douyin_login.parse_request(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("tasks,lease", [({"upload": object()}, 0), ({}, 20)])
async def test_auto_login_cannot_interrupt_active_upload_or_preview(tasks, lease):
    browser = SimpleNamespace(handle=AsyncMock())
    service = douyin_login.LoginService(browser)
    service._content = SimpleNamespace(tasks=tasks, editor_lease_remaining=lambda: lease,
                                       invalidate_editor=lambda: pytest.fail("不得失效活动预览"))
    result = await service.process("recover_login")
    assert result["state"] == "unavailable"
    browser.handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_login_busy_guard_never_waits_then_navigates():
    browser = SimpleNamespace(handle=AsyncMock())
    service = douyin_login.LoginService(browser)
    async with service._browser_lock:
        result = await asyncio.wait_for(service.process("recover_login"), timeout=0.1)
    assert result["state"] == "unavailable"
    browser.handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_auto_login_reuses_existing_login_safety_checks():
    browser = SimpleNamespace(handle=AsyncMock(return_value=douyin_login.make_response("logged_in")))
    service = douyin_login.LoginService(browser)
    service._content = SimpleNamespace(tasks={}, editor_lease_remaining=lambda: 0,
                                       invalidate_editor=lambda: pytest.fail("自动检查不失效预览"))
    assert (await service.process("recover_login"))["state"] == "logged_in"
    browser.handle.assert_awaited_once_with("login")


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
    def __init__(self, uid: int, pid: int = 4321):
        self.credentials = struct.pack("3i", pid, uid, 100)

    def getsockopt(self, level: int, option: int, length: int) -> bytes:
        assert level == socket.SOL_SOCKET
        assert option == socket.SO_PEERCRED
        assert length == struct.calcsize("3i")
        return self.credentials


def test_peer_uid_uses_kernel_peer_credentials(monkeypatch):
    monkeypatch.setattr(douyin_login.socket, "SO_PEERCRED", 17, raising=False)
    assert douyin_login.peer_uid(FakePeerSocket(1001)) == 1001
    assert douyin_login.peer_pid(FakePeerSocket(1001, pid=5432)) == 5432
    assert douyin_login.is_peer_authorized(FakePeerSocket(1001), 1001)
    assert not douyin_login.is_peer_authorized(FakePeerSocket(1002), 1001)


class FakeSystemdProcess:
    def __init__(self, stdout: bytes, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.killed = False

    async def communicate(self):
        return self.stdout, b""

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("peer_process_id", "main_pid", "expected"),
    [(4321, b"4321\n", True), (9876, b"4321\n", False), (4321, b"0\n", False)],
)
async def test_gateway_publish_authorization_matches_systemd_main_pid(
    monkeypatch, peer_process_id, main_pid, expected
):
    command = {}
    process = FakeSystemdProcess(main_pid)

    async def create_subprocess_exec(*args, **kwargs):
        command["args"] = args
        command["kwargs"] = kwargs
        return process

    monkeypatch.setattr(
        douyin_login.asyncio, "create_subprocess_exec", create_subprocess_exec
    )

    assert await douyin_login._gateway_main_pid_matches(peer_process_id) is expected
    assert command["args"] == (
        "systemctl",
        "show",
        "hermes-gateway.service",
        "--property=MainPID",
        "--value",
    )
    assert command["kwargs"]["stdout"] == douyin_login.asyncio.subprocess.PIPE
    assert command["kwargs"]["stderr"] == douyin_login.asyncio.subprocess.DEVNULL
    assert "shell" not in command["kwargs"]


@pytest.mark.asyncio
async def test_gateway_publish_authorization_fails_closed_without_systemd(monkeypatch):
    async def missing_systemctl(*_args, **_kwargs):
        raise FileNotFoundError("systemctl unavailable")

    monkeypatch.setattr(
        douyin_login.asyncio, "create_subprocess_exec", missing_systemctl
    )
    assert not await douyin_login._gateway_main_pid_matches(4321)


@pytest.mark.asyncio
async def test_gateway_publish_authorization_fails_closed_on_timeout(monkeypatch):
    class HangingProcess(FakeSystemdProcess):
        async def communicate(self):
            await asyncio.Event().wait()

    process = HangingProcess(b"")
    process.returncode = None

    async def create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(
        douyin_login.asyncio, "create_subprocess_exec", create_subprocess_exec
    )
    monkeypatch.setattr(douyin_login, "GATEWAY_MAIN_PID_TIMEOUT_SECONDS", 0.001)

    assert not await douyin_login._gateway_main_pid_matches(4321)
    assert process.killed


class FakeStreamReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    async def readline(self):
        return self.payload


class FakeStreamWriter:
    def __init__(self, peer_socket):
        self.peer_socket = peer_socket
        self.response = bytearray()

    def get_extra_info(self, name: str):
        return self.peer_socket if name == "socket" else None

    def write(self, payload: bytes):
        self.response.extend(payload)

    async def drain(self):
        pass

    def close(self):
        pass

    async def wait_closed(self):
        pass


class RecordingService:
    def __init__(self):
        self.actions = []

    async def process(self, action):
        self.actions.append(action)
        return douyin_login.make_response("unknown")


@pytest.mark.asyncio
async def test_socket_publish_from_gateway_main_pid_reaches_service(monkeypatch):
    monkeypatch.setattr(douyin_login.socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.syspath_prepend(str(SERVICE_PATH.parent))
    process = FakeSystemdProcess(b"4321\n")

    async def create_subprocess_exec(*_args, **_kwargs):
        return process

    monkeypatch.setattr(
        douyin_login.asyncio, "create_subprocess_exec", create_subprocess_exec
    )
    payload = (
        b'{"action":"content","request":{"action":"publish","token":"'
        + b"a" * 32
        + b'"}}\n'
    )
    writer = FakeStreamWriter(FakePeerSocket(uid=1001, pid=4321))
    service = RecordingService()

    await douyin_login._handle_connection(
        FakeStreamReader(payload), writer, service, allowed_uid=1001
    )

    assert len(service.actions) == 1
    assert service.actions[0]["action"] == "publish"
    assert json.loads(writer.response)["state"] == "unknown"


@pytest.mark.asyncio
async def test_socket_publish_from_shell_pid_is_rejected_before_service_process(
    monkeypatch,
):
    monkeypatch.setattr(douyin_login.socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.syspath_prepend(str(SERVICE_PATH.parent))

    async def create_subprocess_exec(*_args, **_kwargs):
        return FakeSystemdProcess(b"4321\n")

    monkeypatch.setattr(
        douyin_login.asyncio, "create_subprocess_exec", create_subprocess_exec
    )
    payload = (
        b'{"action":"content","request":{"action":"publish","token":"'
        + b"a" * 32
        + b'"}}\n'
    )
    writer = FakeStreamWriter(FakePeerSocket(uid=1001, pid=9876))
    service = RecordingService()

    await douyin_login._handle_connection(
        FakeStreamReader(payload), writer, service, allowed_uid=1001
    )

    assert service.actions == []
    response = json.loads(writer.response)
    assert response["state"] == "unavailable"
    assert response["message"] == "发布请求仅允许由 gateway 主进程发起。"


@pytest.mark.asyncio
async def test_socket_non_publish_actions_do_not_check_gateway_main_pid(monkeypatch):
    monkeypatch.setattr(douyin_login.socket, "SO_PEERCRED", 17, raising=False)
    monkeypatch.syspath_prepend(str(SERVICE_PATH.parent))

    async def unexpected_main_process_check(_peer_socket):
        pytest.fail("非 publish 操作不应查询 gateway MainPID")

    monkeypatch.setattr(
        douyin_login, "is_peer_gateway_main_process", unexpected_main_process_check
    )
    requests = [
        {"action": "status"},
        {"action": "login"},
        {"action": "content", "request": {"action": "list"}},
        {"action": "content", "request": {"action": "metrics"}},
        {
            "action": "content",
            "request": {"action": "draft", "token": "a" * 32},
        },
        {
            "action": "content",
            "request": {"action": "job", "job_id": "a" * 32},
        },
    ]
    service = RecordingService()

    for request in requests:
        writer = FakeStreamWriter(FakePeerSocket(uid=1001))
        payload = json.dumps(request).encode("utf-8") + b"\n"
        await douyin_login._handle_connection(
            FakeStreamReader(payload), writer, service, allowed_uid=1001
        )

    expected = [
        "status",
        "login",
        {"action": "list"},
        {"action": "metrics"},
        {"action": "draft", "token": "a" * 32},
        {"action": "job", "job_id": "a" * 32},
    ]
    assert service.actions == expected


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


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.wall = 1_700_000_000.0

    def monotonic(self):
        return self.now

    def wall_time(self):
        return self.wall

    def advance(self, seconds: float):
        self.now += seconds
        self.wall += seconds


@pytest.fixture
def missing_manual_window(tmp_path, monkeypatch):
    path = tmp_path / "manual.pass"
    monkeypatch.setattr(douyin_login, "MANUAL_WINDOW_PASSWORD_FILE", path)
    return path


class IdleBrowser:
    def __init__(self):
        self.open = False
        self.close_count = 0

    async def handle(self, _action: str):
        self.open = True
        return douyin_login.make_response("unknown")

    async def close(self):
        self.open = False
        self.close_count += 1


class BlockingCloseBrowser(IdleBrowser):
    def __init__(self):
        super().__init__()
        self.close_started = asyncio.Event()
        self.finish_close = asyncio.Event()

    async def close(self):
        self.close_started.set()
        await self.finish_close.wait()
        await super().close()


class HungContextClose:
    def __init__(self):
        self.close_started = asyncio.Event()

    async def close(self):
        self.close_started.set()
        await asyncio.Event().wait()


class RecordingPlaywrightStop:
    def __init__(self):
        self.stop_calls = 0

    async def stop(self):
        self.stop_calls += 1


def make_idle_service(browser, clock):
    return douyin_login.LoginService(
        browser, clock=clock.monotonic, wall_clock=clock.wall_time
    )


@pytest.mark.asyncio
async def test_idle_browser_closes_and_reopens_lazily(missing_manual_window):
    clock = FakeClock()
    browser = IdleBrowser()
    service = make_idle_service(browser, clock)

    await service.process("status")
    assert browser.open
    clock.advance(douyin_login.BROWSER_IDLE_SECONDS)

    assert await service._close_browser_if_idle()
    assert browser.close_count == 1
    assert not browser.open

    await service.process("status")
    assert browser.open
    assert browser.close_count == 1


@pytest.mark.asyncio
async def test_hung_context_close_times_out_stops_driver_and_releases_lock(
    missing_manual_window, monkeypatch, caplog
):
    clock = FakeClock()
    browser = douyin_login.PlaywrightBrowser(config=None)
    context = HungContextClose()
    playwright = RecordingPlaywrightStop()
    browser._context = context
    browser._playwright = playwright
    service = make_idle_service(browser, clock)
    monkeypatch.setattr(
        douyin_login, "BROWSER_CONTEXT_CLOSE_TIMEOUT_SECONDS", 0.01
    )
    monkeypatch.setattr(douyin_login, "PLAYWRIGHT_STOP_TIMEOUT_SECONDS", 0.01)
    async with service._browser_lock:
        pass
    clock.advance(douyin_login.BROWSER_IDLE_SECONDS)

    assert await service._close_browser_if_idle()

    assert context.close_started.is_set()
    assert playwright.stop_calls == 1
    assert "TimeoutError" in caplog.text
    assert browser._context is None
    assert browser._playwright is None
    assert not service._browser_lock.locked()
    async with service._browser_lock:
        pass


@pytest.mark.asyncio
async def test_browser_operation_refreshes_idle_deadline(missing_manual_window):
    clock = FakeClock()
    browser = IdleBrowser()
    service = make_idle_service(browser, clock)

    await service.process("status")
    clock.advance(douyin_login.BROWSER_IDLE_SECONDS - 10)
    await service.process("status")
    clock.advance(douyin_login.BROWSER_IDLE_SECONDS - 1)

    assert not await service._close_browser_if_idle()
    assert browser.close_count == 0
    clock.advance(1)
    assert await service._close_browser_if_idle()


@pytest.mark.asyncio
async def test_idle_check_waits_for_browser_lock_and_respects_active_operation(
    missing_manual_window,
):
    clock = FakeClock()
    browser = IdleBrowser()
    service = make_idle_service(browser, clock)
    await service.process("status")

    lock_acquired = asyncio.Event()
    release_lock = asyncio.Event()

    async def hold_browser_lock():
        async with service._browser_lock:
            lock_acquired.set()
            await release_lock.wait()

    operation = asyncio.create_task(hold_browser_lock())
    await lock_acquired.wait()
    clock.advance(douyin_login.BROWSER_IDLE_SECONDS)
    idle_check = asyncio.create_task(service._close_browser_if_idle())
    await asyncio.sleep(0)

    assert not idle_check.done()
    assert browser.close_count == 0
    release_lock.set()
    await operation
    assert not await idle_check
    assert browser.close_count == 0


@pytest.mark.asyncio
async def test_idle_monitor_closes_after_fakeclock_deadline(missing_manual_window):
    clock = FakeClock()
    browser = IdleBrowser()
    service = make_idle_service(browser, clock)
    await service.process("status")
    service.start_idle_monitor()
    await asyncio.sleep(0)

    clock.advance(douyin_login.BROWSER_IDLE_SECONDS)
    service._activity_event.set()
    for _ in range(10):
        if browser.close_count:
            break
        await asyncio.sleep(0)

    assert browser.close_count == 1
    assert not browser.open
    await service.stop_idle_monitor()


@pytest.mark.asyncio
async def test_idle_monitor_is_cancelled_and_gathered_on_shutdown():
    service = make_idle_service(IdleBrowser(), FakeClock())
    service.start_idle_monitor()
    task = service._idle_task
    assert task is not None
    await asyncio.sleep(0)

    await service.stop_idle_monitor()

    assert task.done()
    assert task.cancelled()
    assert service._idle_task is None


@pytest.mark.asyncio
async def test_shutdown_waits_for_idle_close_before_releasing_browser_lock(
    missing_manual_window,
):
    clock = FakeClock()
    browser = BlockingCloseBrowser()
    service = make_idle_service(browser, clock)
    await service.process("status")
    service.start_idle_monitor()
    await asyncio.sleep(0)

    clock.advance(douyin_login.BROWSER_IDLE_SECONDS)
    service._activity_event.set()
    await browser.close_started.wait()
    idle_task = service._idle_task
    shutdown = asyncio.create_task(service.stop_idle_monitor())
    await asyncio.sleep(0)

    assert not shutdown.done()
    assert browser.close_count == 0
    browser.finish_close.set()
    await shutdown

    assert browser.close_count == 1
    assert not browser.open
    assert idle_task is not None and idle_task.cancelled()


@pytest.mark.asyncio
async def test_recent_manual_window_temporarily_prevents_idle_close(
    tmp_path, monkeypatch
):
    clock = FakeClock()
    manual_window = tmp_path / "manual.pass"
    manual_window.touch()
    os.utime(manual_window, (clock.wall, clock.wall))
    monkeypatch.setattr(
        douyin_login, "MANUAL_WINDOW_PASSWORD_FILE", manual_window
    )
    browser = IdleBrowser()
    service = make_idle_service(browser, clock)
    await service.process("status")
    clock.advance(douyin_login.BROWSER_IDLE_SECONDS)

    assert not await service._close_browser_if_idle()
    assert browser.close_count == 0

    clock.advance(douyin_login.MANUAL_WINDOW_GRACE_SECONDS)
    assert await service._close_browser_if_idle()
    assert browser.close_count == 1


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
