import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource


def _event(text: str) -> MessageEvent:
    return MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.QQBOT,
            user_id="u1",
            chat_id="c1",
            user_name="tester",
            chat_type="dm",
        ),
        message_id="m1",
    )


@pytest.mark.asyncio
async def test_auxmodel_openai_image_auth_uses_default_image_key_env(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "\n".join(
            [
                "image_gen:",
                "  provider: openai",
                "  model: gpt-image-2-medium",
                "  openai:",
                "    base_url: https://suyuan.4071253.xyz/v1",
                "    model: gpt-image-2-medium",
                "    timeout: 180",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "image-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    result = await runner._handle_auxmodel_command(_event("/auxmodel"))

    assert "image: gpt-image-2-medium" in result
    assert "  provider: openai" in result
    assert "  endpoint: https://suyuan.4071253.xyz/v1" in result
    assert "  auth: OPENAI_IMAGE_API_KEY（已设置）" in result
