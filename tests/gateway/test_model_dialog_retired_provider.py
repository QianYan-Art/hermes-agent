"""验证退役的自定义模型入口不会重新出现在网关列表。"""

from unittest.mock import patch

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["xiaomi-token-plan-cn", "custom:xiaomi-token-plan-cn"])
async def test_retired_custom_provider_is_filtered_without_hiding_allowed_provider(slug):
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._session_model_overrides = {}
    event = MessageEvent(
        text="/model",
        message_type=MessageType.TEXT,
        source=SessionSource(platform=Platform.QQBOT, chat_id="test", chat_type="dm"),
    )
    rows = [
        {"slug": slug, "name": "退役入口", "models": ["retired-model"]},
        {"slug": "openrouter", "name": "保留入口", "models": ["available-model"]},
    ]
    with (
        patch("gateway.run._load_gateway_config", return_value={
            "model": {"default": "kimi-for-coding", "provider": "kimi-code"},
        }),
        patch("hermes_cli.model_switch.list_authenticated_providers", return_value=rows),
    ):
        result = await runner._handle_model_command(event)

    assert "退役入口" not in result
    assert "retired-model" not in result
    assert "保留入口" in result
    assert "available-model" in result
    assert "kimi-for-coding" in result
