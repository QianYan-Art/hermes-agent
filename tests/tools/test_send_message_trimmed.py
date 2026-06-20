import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from gateway.config import Platform
from tools.send_message_tool import _send_to_platform


def test_send_to_qqbot_without_slack_adapter():
    send = AsyncMock(return_value={"success": True, "platform": "qqbot"})
    pconfig = SimpleNamespace(enabled=True, token="tok", extra={})

    with patch("tools.send_message_tool._send_qqbot", send):
        result = asyncio.run(
            _send_to_platform(
                Platform.QQBOT,
                pconfig,
                "chat-id",
                "hello",
            )
        )

    assert result == {"success": True, "platform": "qqbot"}
    send.assert_awaited_once_with(
        pconfig,
        "chat-id",
        "hello",
    )


def test_send_to_slack_without_slack_adapter_returns_clear_error():
    result = asyncio.run(
        _send_to_platform(
            Platform.SLACK,
            SimpleNamespace(enabled=True, token="tok", extra={}),
            "C123",
            "hello",
        )
    )

    assert result == {"error": "Slack adapter is not available in this Hermes build"}
