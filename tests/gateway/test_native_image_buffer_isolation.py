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
    runner._decide_image_input_mode = lambda: "native"
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
    runner._supports_native_video_input = lambda: True
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
    runner._supports_native_video_input = lambda: False
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
    runner._supports_native_video_input = lambda: True
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
