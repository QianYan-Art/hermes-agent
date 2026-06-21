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


def test_send_to_qqbot_media_uses_live_adapter(tmp_path):
    image_path = tmp_path / "result.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    adapter = SimpleNamespace(
        send_image_file=AsyncMock(
            return_value=SimpleNamespace(success=True, message_id="qq-img-1")
        )
    )
    runner = SimpleNamespace(adapters={Platform.QQBOT: adapter})
    pconfig = SimpleNamespace(enabled=True, token="tok", extra={})

    with patch("gateway.run._gateway_runner_ref", return_value=runner), patch(
        "tools.send_message_tool._send_qqbot", AsyncMock()
    ) as text_send:
        result = asyncio.run(
            _send_to_platform(
                Platform.QQBOT,
                pconfig,
                "user-openid",
                "生成好了",
                media_files=[(str(image_path), False)],
            )
        )

    assert result == {
        "success": True,
        "platform": "qqbot",
        "chat_id": "user-openid",
        "message_id": "qq-img-1",
    }
    adapter.send_image_file.assert_awaited_once_with(
        chat_id="user-openid",
        image_path=str(image_path),
        caption="生成好了",
        metadata=None,
    )
    text_send.assert_not_awaited()


def test_send_to_qqbot_media_without_live_adapter_returns_clear_error(tmp_path):
    image_path = tmp_path / "result.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    pconfig = SimpleNamespace(enabled=True, token="tok", extra={})

    with patch("gateway.run._gateway_runner_ref", return_value=None), patch(
        "tools.send_message_tool._send_qqbot", AsyncMock()
    ) as text_send:
        result = asyncio.run(
            _send_to_platform(
                Platform.QQBOT,
                pconfig,
                "user-openid",
                "",
                media_files=[(str(image_path), False)],
            )
        )

    assert result == {
        "error": (
            "QQBot media delivery requires the running gateway QQBot adapter; "
            "the standalone QQBot REST sender supports text only."
        )
    }
    text_send.assert_not_awaited()


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


def test_send_to_signal_without_signal_adapter_returns_clear_error():
    result = asyncio.run(
        _send_to_platform(
            Platform.SIGNAL,
            SimpleNamespace(enabled=True, token="", extra={"account": "+10000000000"}),
            "+10000000000",
            "hello",
        )
    )

    assert result == {"error": "Signal delivery is not available in this Hermes build"}
