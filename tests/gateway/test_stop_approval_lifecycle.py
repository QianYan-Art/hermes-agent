"""停止执行时取消审批等待，但保留已经授予的权限。"""

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.config import Platform
from gateway.run import GatewayRunner
from gateway.session import SessionSource
from tools import approval


@pytest.mark.asyncio
async def test_stop_unblocks_all_pending_commands_and_rejects_old_buttons(monkeypatch):
    key = "qq-stop-approval"
    entries = [approval._ApprovalEntry({"command": "测试命令"}) for _ in range(2)]
    monkeypatch.setattr(approval, "_gateway_queues", {key: entries[:]})
    monkeypatch.setattr(approval, "_pending", {key: {"command": "旧命令"}})
    monkeypatch.setattr(approval, "_session_approved", {key: {"approved-pattern"}})
    monkeypatch.setattr(approval, "_session_yolo", {key})
    results = []
    threads = [threading.Thread(target=lambda e=e: results.append(
        e.result if e.event.wait(1) else "未唤醒")) for e in entries]
    for thread in threads:
        thread.start()

    runner = object.__new__(GatewayRunner)
    agent = SimpleNamespace(interrupt=Mock())
    adapter = SimpleNamespace(interrupt_session_activity=AsyncMock(), get_pending_message=Mock())
    runner._running_agents = {key: agent}
    runner.adapters = {Platform.QQBOT: adapter}
    runner._pending_messages = {key: "旧追问"}
    runner._invalidate_session_run_generation = Mock()
    runner._release_running_agent_state = Mock()
    source = SessionSource(platform=Platform.QQBOT, chat_id="owner", user_id="owner", chat_type="dm")
    await runner._interrupt_and_clear_session(key, source, interrupt_reason="本人停止", invalidation_reason="stop")
    for thread in threads:
        thread.join(1)

    assert results == ["deny", "deny"]
    assert not approval.has_blocking_approval(key)
    assert not approval.resolve_gateway_approval(key, "always")
    assert key not in approval._pending and key not in runner._pending_messages
    assert approval._session_approved[key] == {"approved-pattern"}
    assert key in approval._session_yolo
    agent.interrupt.assert_called_once_with("本人停止")
    adapter.interrupt_session_activity.assert_awaited_once_with(key, "owner")


def test_cancel_pending_preserves_other_sessions_and_ignores_empty_key(monkeypatch):
    entry = approval._ApprovalEntry({"command": "另一会话"})
    monkeypatch.setattr(approval, "_gateway_queues", {"other": [entry]})
    monkeypatch.setattr(approval, "_pending", {"other": {"command": "另一会话"}})
    approval.cancel_pending_approvals("")
    approval.cancel_pending_approvals("absent")
    assert not entry.event.is_set()
    assert "other" in approval._pending
