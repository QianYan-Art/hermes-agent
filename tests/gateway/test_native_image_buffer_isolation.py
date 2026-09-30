import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource, build_session_key


def _make_runner() -> GatewayRunner:
    runner = GatewayRunner.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="fake")},
    )
    runner.adapters = {}
    runner._model = "openai/gpt-4.1-mini"
    runner._base_url = None
    runner._decide_image_input_mode = lambda **_: "native"
    return runner


def _source(chat_id: str) -> SessionSource:
    return SessionSource(
        platform=Platform.TELEGRAM,
        chat_id=chat_id,
        chat_type="private",
        user_name=f"user-{chat_id}",
    )


def _image_event(source: SessionSource, path: str) -> MessageEvent:
    return MessageEvent(
        text="see image",
        message_type=MessageType.PHOTO,
        source=source,
        media_urls=[path],
        media_types=["image/png"],
    )


def _video_event(source: SessionSource, path: str) -> MessageEvent:
    return MessageEvent(
        text="see video",
        message_type=MessageType.VIDEO,
        source=source,
        media_urls=[path],
        media_types=["video/mp4"],
    )


@pytest.mark.asyncio
async def test_native_image_buffer_isolated_per_session():
    runner = _make_runner()
    source_a = _source("chat-a")
    source_b = _source("chat-b")

    await runner._prepare_inbound_message_text(
        event=_image_event(source_a, "/tmp/a.png"),
        source=source_a,
        history=[],
    )
    await runner._prepare_inbound_message_text(
        event=_image_event(source_b, "/tmp/b.png"),
        source=source_b,
        history=[],
    )

    assert runner._consume_pending_native_image_paths(build_session_key(source_a)) == ["/tmp/a.png"]
    assert runner._consume_pending_native_image_paths(build_session_key(source_b)) == ["/tmp/b.png"]


@pytest.mark.asyncio
async def test_native_image_buffer_not_cleared_by_other_sessions_without_images():
    runner = _make_runner()
    source_a = _source("chat-a")
    source_b = _source("chat-b")

    await runner._prepare_inbound_message_text(
        event=_image_event(source_a, "/tmp/a.png"),
        source=source_a,
        history=[],
    )
    await runner._prepare_inbound_message_text(
        event=MessageEvent(text="plain text", source=source_b),
        source=source_b,
        history=[],
    )

    assert runner._consume_pending_native_image_paths(build_session_key(source_a)) == ["/tmp/a.png"]
    assert runner._consume_pending_native_image_paths(build_session_key(source_b)) == []


@pytest.mark.asyncio
async def test_native_video_buffer_isolated_per_session():
    runner = _make_runner()
    runner._supports_native_video_input = lambda **_: True
    source_a = _source("chat-a")
    source_b = _source("chat-b")

    await runner._prepare_inbound_message_text(
        event=_video_event(source_a, "/tmp/a.mp4"),
        source=source_a,
        history=[],
    )
    await runner._prepare_inbound_message_text(
        event=_video_event(source_b, "/tmp/b.mp4"),
        source=source_b,
        history=[],
    )

    assert runner._consume_pending_native_video_paths(build_session_key(source_a)) == ["/tmp/a.mp4"]
    assert runner._consume_pending_native_video_paths(build_session_key(source_b)) == ["/tmp/b.mp4"]


@pytest.mark.asyncio
async def test_video_buffer_not_used_when_model_lacks_native_video():
    runner = _make_runner()
    runner._supports_native_video_input = lambda **_: False
    source = _source("chat-a")

    text = await runner._prepare_inbound_message_text(
        event=_video_event(source, "/tmp/a.mp4"),
        source=source,
        history=[],
    )

    assert "see video" in text
    assert runner._consume_pending_native_video_paths(build_session_key(source)) == []


@pytest.mark.asyncio
async def test_mixed_media_uses_mime_type_not_overall_message_type():
    runner = _make_runner()
    runner._supports_native_video_input = lambda **_: True
    source = _source("chat-a")

    await runner._prepare_inbound_message_text(
        event=MessageEvent(
            text="mixed",
            message_type=MessageType.VIDEO,
            source=source,
            media_urls=["/tmp/clip.mp4", "/tmp/frame.png"],
            media_types=["video/mp4", "image/png"],
        ),
        source=source,
        history=[],
    )

    key = build_session_key(source)
    assert runner._consume_pending_native_video_paths(key) == ["/tmp/clip.mp4"]
    assert runner._consume_pending_native_image_paths(key) == ["/tmp/frame.png"]


@pytest.mark.asyncio
async def test_kimi_media_route_uses_session_override_not_runtime_globals(monkeypatch, tmp_path):
    from agent.image_routing import build_native_content_parts
    from agent.transports.chat_completions import ChatCompletionsTransport

    runner = _make_runner()
    del runner._decide_image_input_mode
    source_a = _source("kimi-chat")
    source_b = _source("other-chat")
    key_a, key_b = build_session_key(source_a), build_session_key(source_b)
    cfg = {
        "model": {"provider": "kimi-code", "default": "kimi-for-coding"},
        "providers": {"kimi-code": {"base_url": "https://api.kimi.com/coding/v1"}},
    }
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: cfg)
    monkeypatch.setattr("gateway.run._resolve_gateway_model", lambda *_: "kimi-for-coding")
    runner._session_model_overrides = {
        key_a: {
            "model": "kimi-for-coding", "provider": "custom", "api_key": "test",
            "base_url": "https://api.kimi.com/coding/v1", "api_mode": "chat_completions",
        },
        key_b: {
            "model": "kimi-for-coding", "provider": "custom", "api_key": "test",
            "base_url": "https://other.example/v1", "api_mode": "chat_completions",
        },
    }
    monkeypatch.setattr("agent.models_dev.get_model_capabilities", lambda *_: None)
    monkeypatch.setattr("agent.auxiliary_client._RUNTIME_MAIN_MODEL", "deepseek-chat")
    monkeypatch.setattr("agent.auxiliary_client._RUNTIME_MAIN_PROVIDER", "deepseek")
    monkeypatch.setattr("agent.auxiliary_client._RUNTIME_MAIN_BASE_URL", "https://other.example/v1")
    assert runner._decide_image_input_mode(session_key=key_a) == "native"
    assert runner._decide_image_input_mode(session_key=key_b) == "text"
    assert runner._supports_native_video_input(session_key=key_a)
    assert not runner._supports_native_video_input(session_key=key_b)

    image = tmp_path / "frame.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    async def forbidden_analysis(*args, **kwargs):
        pytest.fail("Kimi 原生图片不得调用辅助分析")

    runner._analyze_image = forbidden_analysis
    text = await runner._prepare_inbound_message_text(
        event=MessageEvent(
            text="描述这两个附件", message_type=MessageType.VIDEO, source=source_a,
            media_urls=[str(image), str(video)], media_types=["image/png", "video/mp4"],
        ),
        source=source_a, history=[],
    )
    parts, skipped = build_native_content_parts(
        text, runner._consume_pending_native_image_paths(key_a),
        video_paths=runner._consume_pending_native_video_paths(key_a),
    )
    wire = ChatCompletionsTransport().convert_messages([{"role": "user", "content": parts}])
    assert skipped == []
    assert [p["type"] for p in wire[0]["content"]] == ["text", "image_url", "video_url"]
    assert runner._consume_pending_native_image_paths(key_a) == []
    assert runner._consume_pending_native_video_paths(key_a) == []
