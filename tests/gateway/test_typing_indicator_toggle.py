"""平台 typing 指示器开关测试。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
)
from gateway.session import SessionSource, build_session_key


class _StubAdapter(BasePlatformAdapter):
    async def connect(self, *, is_reconnect: bool = False):
        pass

    async def disconnect(self):
        pass

    async def send(self, chat_id, text, **kwargs):
        return None

    async def get_chat_info(self, chat_id):
        return {}


def _make_adapter(typing_indicator: bool) -> _StubAdapter:
    adapter = _StubAdapter(
        PlatformConfig(enabled=True, token="t", typing_indicator=typing_indicator),
        Platform.SLACK,
    )
    adapter.send_typing = AsyncMock(return_value=None)
    adapter._send_with_retry = AsyncMock(return_value=None)
    adapter._message_handler = AsyncMock(return_value="ok")
    return adapter


def _make_event(chat_id="C123"):
    return MessageEvent(
        text="hi",
        message_type=MessageType.TEXT,
        source=SessionSource(platform=Platform.SLACK, chat_id=chat_id, chat_type="dm"),
    )


def _session_key(chat_id="C123"):
    return build_session_key(
        SessionSource(platform=Platform.SLACK, chat_id=chat_id, chat_type="dm")
    )


@pytest.mark.asyncio
async def test_typing_indicator_enabled_spawns_refresh_loop():
    adapter = _make_adapter(typing_indicator=True)

    async def _slow_handler(_event):
        await asyncio.sleep(0.05)
        return "ok"

    adapter._message_handler = _slow_handler
    event = _make_event()
    adapter._active_sessions[_session_key()] = asyncio.Event()

    await adapter._process_message_background(event, _session_key())

    assert adapter.send_typing.await_count >= 1


@pytest.mark.asyncio
async def test_typing_indicator_disabled_never_calls_send_typing():
    adapter = _make_adapter(typing_indicator=False)
    event = _make_event()
    adapter._active_sessions[_session_key()] = asyncio.Event()

    await adapter._process_message_background(event, _session_key())

    adapter.send_typing.assert_not_awaited()
    adapter._send_with_retry.assert_awaited()
