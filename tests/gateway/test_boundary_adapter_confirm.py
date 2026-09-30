"""从 QQ 适配器入口核验会话边界确认，不发送真实平台消息。"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import MessageEvent, SendResult
from gateway.platforms.base import EphemeralReply
from gateway.platforms.qqbot.adapter import QQAdapter
from gateway.run import _AGENT_PENDING_SENTINEL
from gateway.session import SessionSource, build_session_key
from tests.gateway.test_destructive_slash_confirm import _make_runner
from tools import slash_confirm


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["new", "reset"])
@pytest.mark.parametrize("native_buttons", [False, True])
@pytest.mark.parametrize("reply", ["/cancel", "cancel", "/approve", "approve", "/always", "button"])
async def test_adapter_preserves_running_task_and_queue_until_approved(monkeypatch, command, reply, native_buttons):
    source = SessionSource(
        platform=Platform.QQBOT, chat_id="fake-chat", user_id="fake-user", chat_type="dm",
    )
    key = build_session_key(source)
    runner = _make_runner()
    adapter = QQAdapter(PlatformConfig(
        enabled=True, extra={"app_id": "fake", "client_secret": "fake"},
    ))
    adapter._busy_text_mode = "queue"
    adapter._send_with_retry = AsyncMock(return_value=SendResult(success=True, message_id="fake"))
    adapter.send_slash_confirm = AsyncMock(
        return_value=SendResult(success=True, message_id="confirm") if native_buttons else None,
    )
    adapter._start_session_processing = Mock()
    runner.adapters = {Platform.QQBOT: adapter}
    runner._is_user_authorized = lambda _: True
    runner._check_slash_access = lambda *_: None
    runner._is_telegram_topic_root_lobby = lambda _: False
    runner._session_key_for_source = lambda _: key
    runner._running_agents = {key: _AGENT_PENDING_SENTINEL}
    runner._running_agents_ts = {}
    runner._read_user_config = lambda: {"approvals": {"destructive_slash_confirm": True}}
    monkeypatch.setattr("hermes_cli.plugins.invoke_hook", lambda *_a, **_kw: [])
    monkeypatch.setattr("cli.save_config_value", lambda *_: True)
    handler = AsyncMock(return_value="新会话已创建")
    setattr(runner, f"_handle_{command}_command", handler)
    old_guard = asyncio.Event()
    old_task = asyncio.create_task(asyncio.Event().wait())
    adapter._active_sessions[key] = old_guard
    adapter._session_tasks[key] = old_task
    pending = MessageEvent(text="旧队列", source=source)
    adapter._pending_messages[key] = pending
    runner._pending_messages[key] = pending
    adapter.set_message_handler(runner._handle_message)
    slash_confirm.clear(key)

    async def interrupt(*args, **kwargs):
        runner._running_agents.pop(key, None)
        runner._pending_messages.pop(key, None)
        adapter._pending_messages.pop(key, None)

    runner._interrupt_and_clear_session = AsyncMock(side_effect=interrupt)
    try:
        await adapter.handle_message(MessageEvent(text=f"/{command}", source=source))
        assert not old_task.done()
        assert adapter._active_sessions[key] is old_guard
        assert adapter._pending_messages[key] is pending
        assert runner._pending_messages[key] is pending
        assert slash_confirm.get_pending(key) is not None
        runner._interrupt_and_clear_session.assert_not_awaited()
        handler.assert_not_awaited()
        adapter._start_session_processing.assert_not_called()

        if reply == "button":
            pending_confirm = slash_confirm.get_pending(key)
            await slash_confirm.resolve(key, pending_confirm["confirm_id"], "once")
        else:
            await adapter.handle_message(MessageEvent(text=reply, source=source))
        assert slash_confirm.get_pending(key) is None
        if reply in {"/cancel", "cancel"}:
            assert not old_task.done()
            assert adapter._active_sessions[key] is old_guard
            assert adapter._pending_messages[key] is pending
            assert runner._pending_messages[key] is pending
            runner._interrupt_and_clear_session.assert_not_awaited()
            handler.assert_not_awaited()
        else:
            assert old_task.cancelled()
            assert key not in adapter._active_sessions
            assert key not in adapter._pending_messages
            assert key not in runner._pending_messages
            runner._interrupt_and_clear_session.assert_awaited_once()
            handler.assert_awaited_once()
        adapter._start_session_processing.assert_not_called()
    finally:
        slash_confirm.clear(key)
        old_task.cancel()
        await asyncio.gather(old_task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_failed_prompt_send_drains_queue_when_original_task_has_exited(cancelled):
    source = SessionSource(platform=Platform.QQBOT, chat_id="fake", user_id="fake", chat_type="dm")
    key = build_session_key(source)
    adapter = QQAdapter(PlatformConfig(enabled=True, extra={"app_id": "fake", "client_secret": "fake"}))
    original_task = asyncio.create_task(asyncio.Event().wait())
    adapter._session_tasks[key] = original_task
    adapter._active_sessions[key] = asyncio.Event()
    queued = MessageEvent(text="期间到达的新消息", source=source)
    adapter._start_session_processing = Mock(return_value=True)

    async def handle(_event):
        original_task.cancel()
        await asyncio.gather(original_task, return_exceptions=True)
        adapter._session_tasks.pop(key, None)
        adapter._pending_messages[key] = queued
        return EphemeralReply("确认提示", session_boundary_completed=False, slash_confirm_id="old")

    error = asyncio.CancelledError() if cancelled else RuntimeError("合成发送故障")
    adapter._send_with_retry = AsyncMock(side_effect=error)
    adapter.set_message_handler(handle)
    slash_confirm.register(key, "old", "new", AsyncMock())
    try:
        with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
            await adapter._dispatch_active_session_command(
                MessageEvent(text="/new", source=source), key, "new",
            )
        assert key not in adapter._active_sessions
        assert key not in adapter._pending_messages
        assert key not in adapter._session_command_guards
        assert slash_confirm.get_pending(key) is None
        adapter._start_session_processing.assert_called_once_with(queued, key)
    finally:
        slash_confirm.clear(key)
        original_task.cancel()
        await asyncio.gather(original_task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("send_error", [False, True])
async def test_deferred_command_does_not_replace_guard_owned_by_new_drain_task(send_error):
    source = SessionSource(platform=Platform.QQBOT, chat_id="fake", user_id="fake", chat_type="dm")
    key = build_session_key(source)
    adapter = QQAdapter(PlatformConfig(enabled=True, extra={"app_id": "fake", "client_secret": "fake"}))
    original_guard = asyncio.Event()
    original_task = asyncio.create_task(asyncio.Event().wait())
    adapter._active_sessions[key] = original_guard
    adapter._session_tasks[key] = original_task
    adapter._send_with_retry = AsyncMock(
        side_effect=RuntimeError("合成发送故障") if send_error else None,
        return_value=SendResult(success=True, message_id="fake"),
    )
    replacement = {}

    async def handle(_event):
        original_task.cancel()
        await asyncio.gather(original_task, return_exceptions=True)
        replacement["guard"] = adapter._active_sessions[key]
        replacement["task"] = asyncio.create_task(asyncio.Event().wait())
        adapter._session_tasks[key] = replacement["task"]
        return EphemeralReply("确认提示", ttl_seconds=0, session_boundary_completed=False)

    adapter.set_message_handler(handle)
    try:
        if send_error:
            with pytest.raises(RuntimeError, match="合成发送故障"):
                await adapter._dispatch_active_session_command(
                    MessageEvent(text="/new", source=source), key, "new",
                )
        else:
            await adapter._dispatch_active_session_command(
                MessageEvent(text="/new", source=source), key, "new",
            )
        assert adapter._active_sessions[key] is replacement["guard"]
        assert adapter._active_sessions[key] is not original_guard
        assert not replacement["task"].done()
        assert key not in adapter._session_command_guards
        adapter._release_session_guard(key, guard=replacement["guard"])
        assert key not in adapter._active_sessions
    finally:
        original_task.cancel()
        if "task" in replacement:
            replacement["task"].cancel()
        await asyncio.gather(original_task, *([replacement["task"]] if "task" in replacement else []), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("busy", [False, True])
@pytest.mark.parametrize("failure", ["result", "exception"])
async def test_undelivered_boundary_confirm_is_revoked_without_reset(monkeypatch, busy, failure):
    source = SessionSource(platform=Platform.QQBOT, chat_id="fake", user_id="fake", chat_type="dm")
    key = build_session_key(source)
    runner = _make_runner()
    adapter = QQAdapter(PlatformConfig(enabled=True, extra={"app_id": "fake", "client_secret": "fake"}))
    adapter._send_with_retry = AsyncMock(
        side_effect=RuntimeError("合成发送故障") if failure == "exception" else None,
        return_value=SendResult(success=False, error="合成发送故障"),
    )
    adapter.send_slash_confirm = AsyncMock(return_value=None)
    adapter.send_typing = AsyncMock()
    runner.adapters = {Platform.QQBOT: adapter}
    runner._is_user_authorized = lambda _: True
    runner._check_slash_access = lambda *_: None
    runner._is_telegram_topic_root_lobby = lambda _: False
    runner._session_key_for_source = lambda _: key
    runner._running_agents = {key: _AGENT_PENDING_SENTINEL} if busy else {}
    runner._running_agents_ts = {}
    runner._read_user_config = lambda: {"approvals": {"destructive_slash_confirm": True}}
    monkeypatch.setattr("hermes_cli.plugins.invoke_hook", lambda *_a, **_kw: [])
    runner._handle_new_command = AsyncMock()
    runner._interrupt_and_clear_session = AsyncMock()
    adapter.set_message_handler(runner._handle_message)
    old_task = asyncio.create_task(asyncio.Event().wait()) if busy else None
    old_guard = asyncio.Event()
    adapter._active_sessions[key] = old_guard
    if old_task is not None:
        adapter._session_tasks[key] = old_task
    slash_confirm.clear(key)
    try:
        event = MessageEvent(text="/new", source=source)
        if busy:
            await adapter.handle_message(event)
            assert adapter._active_sessions[key] is old_guard
            assert not old_task.done()
        else:
            await adapter._process_message_background(event, key)
        adapter._send_with_retry.assert_awaited()
        assert slash_confirm.get_pending(key) is None
        assert await slash_confirm.resolve(key, "1", "once") is None
        runner._handle_new_command.assert_not_awaited()
        runner._interrupt_and_clear_session.assert_not_awaited()
    finally:
        slash_confirm.clear(key)
        if old_task is not None:
            old_task.cancel()
            await asyncio.gather(old_task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["result", "exception", "cancel"])
async def test_failed_confirm_delivery_preserves_newer_confirmation(failure):
    adapter = QQAdapter(PlatformConfig(enabled=True, extra={"app_id": "fake", "client_secret": "fake"}))
    key = "isolated-confirm"
    handler = AsyncMock()
    slash_confirm.register(key, "old", "new", handler)

    async def send(**_kwargs):
        slash_confirm.register(key, "newer", "reset", handler)
        if failure == "exception":
            raise RuntimeError("合成发送故障")
        if failure == "cancel":
            raise asyncio.CancelledError()
        return SendResult(success=False)

    adapter._send_with_retry = send
    response = EphemeralReply("确认提示", slash_confirm_id="old")
    try:
        if failure == "result":
            assert not (await adapter._send_handler_reply(response, key, chat_id="fake", content=response)).success
        else:
            with pytest.raises(RuntimeError if failure == "exception" else asyncio.CancelledError):
                await adapter._send_handler_reply(response, key, chat_id="fake", content=response)
        assert slash_confirm.get_pending(key)["confirm_id"] == "newer"
        handler.assert_not_awaited()
    finally:
        slash_confirm.clear(key)
