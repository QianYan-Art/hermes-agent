"""Async delegation tests."""

import json
import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from tools import async_delegation as ad
from tools.process_registry import format_process_notification, process_registry


@pytest.fixture(autouse=True)
def _clean_async_state():
    ad._reset_for_tests()
    while not process_registry.completion_queue.empty():
        process_registry.completion_queue.get_nowait()
    yield
    ad._reset_for_tests()
    while not process_registry.completion_queue.empty():
        process_registry.completion_queue.get_nowait()


def _drain_one(timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_registry.completion_queue.empty():
            return process_registry.completion_queue.get_nowait()
        time.sleep(0.02)
    return None


def test_dispatch_returns_handle_then_completion_event():
    def runner():
        return {
            "status": "completed",
            "summary": "done",
            "api_calls": 2,
            "duration_seconds": 0.1,
            "model": "m",
        }

    res = ad.dispatch_async_delegation(
        goal="g",
        context="ctx",
        toolsets=["terminal"],
        role="leaf",
        model="m",
        session_key="agent:main:qq:dm:123",
        runner=runner,
        max_async_children=3,
    )

    assert res["status"] == "dispatched"
    assert res["delegation_id"].startswith("deleg_")
    evt = _drain_one()
    assert evt is not None
    assert evt["type"] == "async_delegation"
    assert evt["summary"] == "done"
    assert evt["session_key"] == "agent:main:qq:dm:123"
    text = format_process_notification(evt)
    assert "ASYNC DELEGATION COMPLETE" in text
    assert "Original goal: g" in text
    assert "ctx" in text


def test_dispatch_rejects_at_capacity():
    gate = threading.Event()

    def blocker():
        gate.wait(timeout=5)
        return {"status": "completed", "summary": "x"}

    first = ad.dispatch_async_delegation(
        goal="a",
        context=None,
        toolsets=None,
        role="leaf",
        model="m",
        session_key="",
        runner=blocker,
        max_async_children=1,
    )
    second = ad.dispatch_async_delegation(
        goal="b",
        context=None,
        toolsets=None,
        role="leaf",
        model="m",
        session_key="",
        runner=blocker,
        max_async_children=1,
    )
    gate.set()

    assert first["status"] == "dispatched"
    assert second["status"] == "rejected"
    assert "capacity reached" in second["error"]


def test_delegate_task_background_routes_without_blocking():
    import tools.delegate_tool as dt

    parent = MagicMock()
    parent._delegate_depth = 0
    parent.session_id = "sess"
    parent._interrupt_requested = False
    fake_child = MagicMock()
    fake_child._delegate_role = "leaf"
    fake_child._subagent_id = "s1"
    gate = threading.Event()

    def slow_child(task_index, goal, child=None, parent_agent=None, **kw):
        gate.wait(timeout=5)
        return {
            "task_index": 0,
            "status": "completed",
            "summary": f"done: {goal}",
            "api_calls": 1,
            "duration_seconds": 0.1,
            "model": "m",
        }

    creds = {
        "model": "m",
        "provider": None,
        "base_url": None,
        "api_key": None,
        "api_mode": None,
        "command": None,
        "args": None,
    }
    with patch.object(dt, "_build_child_agent", return_value=fake_child), patch.object(
        dt, "_run_single_child", side_effect=slow_child
    ), patch.object(dt, "_resolve_delegation_credentials", return_value=creds):
        out = dt.delegate_task(
            goal="real task",
            context="ctx",
            toolsets=["terminal"],
            background=True,
            parent_agent=parent,
        )

    parsed = json.loads(out)
    assert parsed["status"] == "dispatched"
    assert parsed["mode"] == "background"
    assert process_registry.completion_queue.empty()
    assert ad.active_count() == 1

    gate.set()
    evt = _drain_one()
    assert evt is not None
    assert evt["type"] == "async_delegation"
    assert evt["summary"] == "done: real task"


def test_delegate_task_background_rejects_json_string_batch():
    import tools.delegate_tool as dt

    parent = MagicMock()
    parent._delegate_depth = 0
    out = dt.delegate_task(
        tasks=json.dumps([{"goal": "a"}, {"goal": "b"}]),
        background=True,
        parent_agent=parent,
    )

    parsed = json.loads(out)
    assert "error" in parsed
    assert "single-task only" in parsed["error"]


def test_gateway_watch_drain_requeues_async_events():
    from gateway.run import _drain_gateway_watch_events

    q = queue.Queue()
    async_evt = {"type": "async_delegation", "delegation_id": "deleg_x"}
    watch_evt = {"type": "watch_match", "session_id": "proc_1"}
    q.put(async_evt)
    q.put(watch_evt)

    assert _drain_gateway_watch_events(q) == [watch_evt]
    assert q.qsize() == 1
    assert q.get_nowait() == async_evt
