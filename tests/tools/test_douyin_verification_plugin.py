"""发布验证码的本人范围、队列前消费与无明文持久化契约。"""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.config import Platform
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType
from gateway.session import SessionSource
from gateway.session_context import clear_session_vars, set_session_vars

SPEC = importlib.util.spec_from_file_location("douyin_verification_plugin_test", Path(__file__).parents[2] / "ops/douyin-plugin/__init__.py")
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)
JOB = "c" * 32
SCOPE = ("qqbot", "owner", "owner", "dm")
SAMPLE = "135790"


@pytest.fixture(autouse=True)
def owner_context(monkeypatch):
    monkeypatch.setenv("DOUYIN_OWNER_QQ_USER_ID", "owner")
    tokens = set_session_vars(platform="qqbot", user_id="owner", chat_id="owner", session_key="agent:main:qqbot:dm:owner")
    plugin._VERIFICATIONS.clear()
    plugin._VERIFICATION_MESSAGES.clear()
    yield
    clear_session_vars(tokens)
    plugin._VERIFICATIONS.clear()
    plugin._VERIFICATION_MESSAGES.clear()
    assert not plugin._VERIFICATION_TASKS


def binding(**changes):
    now = plugin.time.monotonic()
    value = {"job_id": JOB, "requested_at": now - 61, "expires_at": now + 300, "requesting": False, "sms_ready": True, "processing": False}
    value.update(changes)
    plugin._VERIFICATIONS[SCOPE] = value
    return value


def event(*, user="owner", chat="owner", chat_type="dm", nonce="sms-1", internal=False):
    value = MessageEvent(text=SAMPLE, source=SessionSource(platform=Platform.QQBOT, user_id=user, chat_id=chat, chat_type=chat_type),
                         message_type=MessageType.TEXT, message_id=nonce, raw_message={"content": SAMPLE})
    value.internal = internal
    return value


async def drain():
    if plugin._VERIFICATION_TASKS:
        await asyncio.gather(*list(plugin._VERIFICATION_TASKS))
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_request_sms_binds_only_valid_job_and_never_accepts_code_parameter(monkeypatch):
    request = AsyncMock(return_value={"ok": True, "state": "ready", "message": "已请求", "job": {"job_id": JOB}})
    monkeypatch.setattr(plugin, "_request_content", request)
    rejected = json.loads(await plugin.handle_verification({"job_id": JOB, "code": SAMPLE}))
    assert rejected["state"] == "needs_attention"
    request.assert_not_awaited()
    result = json.loads(await plugin.handle_verification({"job_id": JOB}))
    assert result["state"] == "ready" and SAMPLE not in json.dumps(result)
    request.assert_awaited_once_with({"action": "verification_request_sms", "job_id": JOB})
    assert SAMPLE not in repr(plugin._VERIFICATIONS)
    await plugin.handle_verification({"job_id": JOB})
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_non_owner_tool_context_cannot_request_sms(monkeypatch):
    tokens = set_session_vars(platform="qqbot", user_id="other", chat_id="other", session_key="agent:main:qqbot:dm:other")
    request = AsyncMock()
    monkeypatch.setattr(plugin, "_request_content", request)
    try:
        result = json.loads(await plugin.handle_verification({"job_id": JOB}))
        assert result["state"] == "unavailable"
        request.assert_not_awaited()
    finally:
        clear_session_vars(tokens)


@pytest.mark.asyncio
async def test_real_adapter_entry_consumes_code_before_active_queue_or_model(monkeypatch, caplog):
    from hermes_cli import plugins
    binding()
    requests = []

    async def request(payload):
        requests.append(dict(payload))
        if payload["action"] == "verification_submit":
            return {"ok": True, "state": "in_progress", "message": "已提交验证", "verification_submitted": True}
        return {"ok": True, "state": "published", "message": "提交发布成功"}

    monkeypatch.setattr(plugin, "_request_content", request)
    adapter = SimpleNamespace(_message_handler=AsyncMock(), _send_with_retry=AsyncMock(), _active_sessions={"busy": object()})
    monkeypatch.setattr(plugins, "invoke_hook", lambda name, **kwargs: [plugin._consume_verification_message(**kwargs)] if name == "pre_gateway_enqueue" else [])
    received = event()
    await BasePlatformAdapter.handle_message(adapter, received)
    await drain()
    assert received.text != SAMPLE and received.raw_message is None
    adapter._message_handler.assert_not_awaited()
    assert requests == [{"action": "verification_submit", "job_id": JOB, "code": SAMPLE}, {"action": "job", "job_id": JOB}]
    assert SAMPLE not in caplog.text and SAMPLE not in repr(plugin._VERIFICATIONS)
    assert SAMPLE not in repr(adapter._send_with_retry.call_args_list)
    assert not plugin._VERIFICATIONS
    assert adapter._active_sessions.keys() == {"busy"}
    assert plugin._consume_verification_message(event=event(), adapter=adapter)["action"] == "skip"
    assert len(requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"user": "other"}, {"chat": "group", "chat_type": "group"}, {"internal": True}])
async def test_other_sources_never_submit_or_consume_verification(monkeypatch, changes):
    binding()
    request = AsyncMock()
    monkeypatch.setattr(plugin, "_request_content", request)
    adapter = SimpleNamespace(_send_with_retry=AsyncMock())
    assert plugin._consume_verification_message(event=event(**changes), adapter=adapter) is None
    request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"expires_at": 0}, {"processing": True}])
async def test_expired_or_busy_binding_drops_sensitive_text_with_fixed_notice(monkeypatch, changes):
    binding(**changes)
    request = AsyncMock()
    monkeypatch.setattr(plugin, "_request_content", request)
    adapter = SimpleNamespace(_send_with_retry=AsyncMock())
    received = event()
    assert plugin._consume_verification_message(event=received, adapter=adapter)["action"] == "skip"
    await drain()
    assert received.text != SAMPLE and received.raw_message is None
    request.assert_not_awaited()
    assert SAMPLE not in repr(adapter._send_with_retry.call_args_list)


def test_missing_message_identity_cannot_leak_code_to_model():
    binding()
    received = event(nonce=None)
    assert plugin._consume_verification_message(event=received, adapter=SimpleNamespace())["action"] == "skip"
    assert received.text != SAMPLE and received.raw_message is None


@pytest.mark.asyncio
async def test_code_can_arrive_while_sms_response_is_still_in_flight(monkeypatch):
    pending = binding(requesting=True, sms_ready=False)
    request = AsyncMock(return_value={"ok": False, "state": "needs_attention", "message": "测试中断"})
    monkeypatch.setattr(plugin, "_request_content", request)
    received = event()
    assert plugin._consume_verification_message(event=received, adapter=SimpleNamespace(_send_with_retry=AsyncMock()))["action"] == "skip"
    await asyncio.sleep(0)
    request.assert_not_awaited()
    pending.update(requesting=False, sms_ready=True)
    await drain()
    request.assert_awaited_once()
    assert request.await_args.args[0]["code"] == SAMPLE


@pytest.mark.asyncio
async def test_request_cancellation_does_not_leave_permanent_requesting_state(monkeypatch):
    monkeypatch.setattr(plugin, "_request_content", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await plugin.handle_verification({"job_id": JOB})
    assert not plugin._VERIFICATIONS[SCOPE]["requesting"]
    assert plugin._VERIFICATIONS[SCOPE]["expires_at"] == 0
    result = json.loads(await plugin.handle_verification({"job_id": JOB}))
    assert result["state"] == "needs_attention"


@pytest.mark.asyncio
async def test_unhandled_messages_continue_after_pre_enqueue_hook(monkeypatch):
    from hermes_cli import plugins
    marker = RuntimeError("已抵达原有处理链")
    adapter = SimpleNamespace(_message_handler=AsyncMock(), _apply_topic_recovery=Mock(side_effect=marker))
    monkeypatch.setattr(plugins, "invoke_hook", lambda *args, **kwargs: [None])
    received = event()
    received.text = "查询原任务"
    with pytest.raises(RuntimeError, match="原有处理链"):
        await BasePlatformAdapter.handle_message(adapter, received)


@pytest.mark.asyncio
async def test_no_binding_code_is_consumed_without_model_or_submit(monkeypatch):
    request = AsyncMock()
    monkeypatch.setattr(plugin, "_request_content", request)
    adapter = SimpleNamespace(_send_with_retry=AsyncMock())
    received = event()
    assert plugin._consume_verification_message(event=received, adapter=adapter)["action"] == "skip"
    await drain()
    assert received.text != SAMPLE and received.raw_message is None
    request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("hook_fails", [True, False])
async def test_core_fails_closed_if_hook_missing_or_raises(monkeypatch, hook_fails):
    from hermes_cli import plugins
    def hook(*args, **kwargs):
        if hook_fails:
            raise RuntimeError("测试回调失败")
        return []
    monkeypatch.setattr(plugins, "invoke_hook", hook)
    adapter = SimpleNamespace(_message_handler=AsyncMock(), _send_with_retry=AsyncMock())
    received = event()
    await BasePlatformAdapter.handle_message(adapter, received)
    assert received.text != SAMPLE and received.raw_message is None
    adapter._message_handler.assert_not_awaited()
    adapter._send_with_retry.assert_awaited_once()


@pytest.mark.asyncio
async def test_early_code_is_not_submitted_when_sms_request_fails(monkeypatch):
    pending = binding(requesting=True, sms_ready=False)
    request = AsyncMock()
    monkeypatch.setattr(plugin, "_request_content", request)
    adapter = SimpleNamespace(_send_with_retry=AsyncMock())
    assert plugin._consume_verification_message(event=event(), adapter=adapter)["action"] == "skip"
    await asyncio.sleep(0)
    pending.update(requesting=False, expires_at=0)
    await drain()
    request.assert_not_awaited()
    assert "未提交" in adapter._send_with_retry.call_args.kwargs["content"]
