"""验证真实 QQ 重连循环，不以本地常量集合代替行为断言。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import gateway.platforms.qqbot.adapter as qq
from gateway.config import PlatformConfig


def _adapter(monkeypatch):
    adapter = qq.QQAdapter(PlatformConfig(
        enabled=True, extra={"app_id": "test", "client_secret": "test"},
    ))
    adapter._running = True
    adapter._mark_transport_disconnected = Mock()
    adapter._fail_pending = Mock()
    adapter._set_fatal_error = Mock()
    adapter._reconnect = AsyncMock(return_value=True)
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(qq, "time", SimpleNamespace(monotonic=lambda: clock.value))
    return adapter, clock


@pytest.mark.asyncio
async def test_successful_socket_reopens_do_not_reset_quick_disconnect_limit(monkeypatch):
    adapter, clock = _adapter(monkeypatch)
    calls = 0

    async def read():
        nonlocal calls
        calls += 1
        clock.value += 0.1
        if calls > qq.MAX_QUICK_DISCONNECT_COUNT + 1:
            adapter._running = False
        raise qq.QQCloseError(4009)

    adapter._read_events = read
    await adapter._listen_loop()

    assert calls == qq.MAX_QUICK_DISCONNECT_COUNT
    assert adapter._reconnect.await_count == qq.MAX_QUICK_DISCONNECT_COUNT - 1
    adapter._set_fatal_error.assert_called_once()
    assert adapter._set_fatal_error.call_args.args[0] == "qq_quick_disconnect"
    assert adapter._mark_transport_disconnected.call_count == calls


@pytest.mark.asyncio
async def test_stable_connection_resets_quick_disconnect_limit(monkeypatch):
    adapter, clock = _adapter(monkeypatch)
    durations = iter(
        [0.1] * (qq.MAX_QUICK_DISCONNECT_COUNT - 1)
        + [qq.QUICK_DISCONNECT_THRESHOLD + 1]
        + [0.1] * (qq.MAX_QUICK_DISCONNECT_COUNT - 1)
    )

    async def read():
        duration = next(durations, None)
        if duration is None:
            adapter._running = False
            return
        clock.value += duration
        raise qq.QQCloseError(4009)

    adapter._read_events = read
    await adapter._listen_loop()
    adapter._set_fatal_error.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("code,kept", [(4009, True), (4006, False), (4007, False)])
async def test_session_resume_state_follows_actual_close_loop(monkeypatch, code, kept):
    adapter, clock = _adapter(monkeypatch)
    adapter._session_id = "existing-session"
    adapter._last_seq = 42

    async def read():
        clock.value += qq.QUICK_DISCONNECT_THRESHOLD + 1
        raise qq.QQCloseError(code)

    async def reconnect(_):
        adapter._running = False
        return True

    adapter._read_events = read
    adapter._reconnect = AsyncMock(side_effect=reconnect)
    await adapter._listen_loop()

    assert adapter._session_id == ("existing-session" if kept else None)
    assert adapter._last_seq == (42 if kept else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [4013, 4014, 4914, 4915])
async def test_fatal_close_stops_actual_reconnect_loop(monkeypatch, code):
    adapter, _ = _adapter(monkeypatch)
    adapter._read_events = AsyncMock(side_effect=qq.QQCloseError(code))
    await adapter._listen_loop()
    adapter._reconnect.assert_not_awaited()
    adapter._set_fatal_error.assert_called_once()
    assert adapter._set_fatal_error.call_args.kwargs["retryable"] is False
