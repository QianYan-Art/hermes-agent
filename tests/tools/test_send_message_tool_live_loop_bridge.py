"""Focused regression tests for live-adapter event-loop bridging."""

import asyncio
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform
from tools.send_message_tool import _send_qqbot_via_adapter, _send_via_adapter


class _FakePlatform:
    """Minimal stand-in for a platform enum entry used by _send_via_adapter."""

    def __init__(self, value):
        self.value = value


@pytest.mark.asyncio
async def test_send_via_adapter_schedules_live_send_on_gateway_loop(monkeypatch):
    platform = _FakePlatform("fakeplatform")
    adapter = SimpleNamespace(
        send=AsyncMock(return_value=SimpleNamespace(success=True, message_id="live-42"))
    )
    runner = SimpleNamespace(
        adapters={platform: adapter},
        _gateway_loop=object(),
    )
    scheduled = {}

    def fake_schedule(coro, loop, *, logger=None, log_message=None, log_level=None):
        scheduled["loop"] = loop
        scheduled["log_message"] = log_message
        if asyncio.iscoroutine(coro):
            coro.close()
        future = Future()
        future.set_result(SimpleNamespace(success=True, message_id="live-42"))
        return future

    monkeypatch.setattr("gateway.run._gateway_runner_ref", lambda: runner)
    monkeypatch.setattr("tools.send_message_tool.safe_schedule_threadsafe", fake_schedule)

    result = await _send_via_adapter(
        platform,
        SimpleNamespace(extra={}),
        "chat-1",
        "hello",
        thread_id="thread-7",
    )

    assert result == {"success": True, "message_id": "live-42"}
    adapter.send.assert_called_once_with(
        chat_id="chat-1",
        content="hello",
        metadata={"thread_id": "thread-7"},
    )
    assert scheduled["loop"] is runner._gateway_loop
    assert scheduled["log_message"] == "fakeplatform live adapter send scheduling error"


@pytest.mark.asyncio
async def test_send_qqbot_via_adapter_schedules_media_send_on_gateway_loop(
    monkeypatch, tmp_path
):
    image_path = tmp_path / "hello.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    adapter = SimpleNamespace(
        send_image_file=AsyncMock(
            return_value=SimpleNamespace(success=True, message_id="qq-live-1")
        )
    )
    runner = SimpleNamespace(
        adapters={Platform.QQBOT: adapter},
        _gateway_loop=object(),
    )
    scheduled = {}

    def fake_schedule(coro, loop, *, logger=None, log_message=None, log_level=None):
        scheduled["loop"] = loop
        scheduled["log_message"] = log_message
        if asyncio.iscoroutine(coro):
            coro.close()
        future = Future()
        future.set_result(SimpleNamespace(success=True, message_id="qq-live-1"))
        return future

    monkeypatch.setattr("gateway.run._gateway_runner_ref", lambda: runner)
    monkeypatch.setattr("tools.send_message_tool.safe_schedule_threadsafe", fake_schedule)

    result = await _send_qqbot_via_adapter(
        "chat-qq",
        "caption",
        media_files=[(str(image_path), False)],
    )

    assert result["success"] is True
    assert result["platform"] == "qqbot"
    assert result["chat_id"] == "chat-qq"
    assert result["message_id"] == "qq-live-1"
    adapter.send_image_file.assert_called_once_with(
        chat_id="chat-qq",
        metadata=None,
        image_path=str(image_path),
        caption="caption",
    )
    assert scheduled["loop"] is runner._gateway_loop
    assert scheduled["log_message"] == "QQBot media send scheduling error"
