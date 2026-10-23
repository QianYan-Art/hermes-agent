"""作品协议与持久任务边界；不连接真实抖音，不将模拟结果当作发布验收。"""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def content(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "ops/douyin-login"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("dy_content_test", directory / "content.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("payload", [
    {"action": "publish", "token": "a" * 32, "confirmed": True},
    {"action": "prepare", "release_id": "../profile"},
    {"action": "draft", "token": "short"},
    {"action": "job", "job_id": "C:/private"},
    {"action": "metrics", "url": "https://example.org"},
    {"action": "prepare", "release_id": "ep00", "title": ""},
    {"action": "prepare", "release_id": "ep00", "description": "x" * 1001},
    [], {"action": "delete"},
])
def test_rejects_expanded_or_invalid_content_protocol(content, payload):
    with pytest.raises(ValueError):
        content.validate_request(payload)


@pytest.fixture
def manager(content, tmp_path, monkeypatch):
    release = {"release_id": "ep00", "title": "序栞", "description": "星栞书库", "ai_generated": True,
               "video_sha256": "a" * 64, "video_path": tmp_path / "video.mp4"}
    store = SimpleNamespace(load=lambda release_id: dict(release), list_releases=lambda: [{"release_id": "ep00"}])
    monkeypatch.setattr(content, "ReleaseStore", lambda data_dir: store)
    browser = SimpleNamespace(config=SimpleNamespace(data_dir=tmp_path, expected_account="expected"), _context=None)
    result = content.ContentManager(browser, asyncio.Lock())

    class Page:
        async def goto(self, *args, **kwargs):
            pass

        async def wait_for_timeout(self, milliseconds):
            pass

        async def evaluate(self, script):
            return []

    async def page():
        return Page()

    async def ui(page):
        return {"buttons": [], "inputs": [], "labels": [], "editable": [], "text_tail": ""}

    monkeypatch.setattr(result, "_account_page", page)
    monkeypatch.setattr(result, "_ui", ui)
    result.test_release = release
    return result


@pytest.mark.asyncio
async def test_prepare_binds_metadata_content_and_account_without_starting_job(manager):
    result = await manager.process({"action": "prepare", "release_id": "ep00", "title": "新版标题"})
    assert result["state"] == "ready"
    token = result["plan"]["token"]
    plan, release = manager._plan(token)
    assert plan["title"] == "新版标题" and plan["account"] == "expected"
    assert plan["video_sha256"] == release["video_sha256"]
    assert manager.jobs == {}
    assert "account" not in result["plan"] and "video_path" not in result["plan"]


@pytest.mark.asyncio
async def test_publish_requires_saved_draft_even_with_valid_token(manager):
    prepared = await manager.process({"action": "prepare", "release_id": "ep00"})
    result = await manager.process({"action": "publish", "token": prepared["plan"]["token"]})
    assert result["state"] == "needs_attention"
    assert manager.jobs == {}


@pytest.mark.asyncio
async def test_content_or_account_drift_invalidates_plan(manager):
    prepared = await manager.process({"action": "prepare", "release_id": "ep00"})
    manager.test_release["video_sha256"] = "b" * 64
    result = await manager.process({"action": "draft", "token": prepared["plan"]["token"]})
    assert result["state"] == "needs_attention" and not manager.jobs


@pytest.mark.asyncio
async def test_expired_plan_cannot_start_operation(manager, content):
    prepared = await manager.process({"action": "prepare", "release_id": "ep00"})
    token = prepared["plan"]["token"]
    path = manager.plan_dir / (token + ".json")
    plan = content._read_json(path)
    plan["expires_unix"] = 0
    content._write_json(path, plan)
    result = await manager.process({"action": "draft", "token": token})
    assert result["state"] == "needs_attention" and not manager.jobs


@pytest.mark.asyncio
async def test_duplicate_request_has_one_persistent_job_and_cancel_is_unknown(manager, monkeypatch, content):
    prepared = await manager.process({"action": "prepare", "release_id": "ep00"})
    token = prepared["plan"]["token"]
    started = asyncio.Event()

    async def execute(*args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(manager, "_execute", execute)
    first = await manager.process({"action": "draft", "token": token})
    await started.wait()
    second = await manager.process({"action": "draft", "token": token})
    assert first["job"]["job_id"] == second["job"]["job_id"]
    assert len(manager.jobs) == 1
    await manager.close()
    job_id = first["job"]["job_id"]
    assert manager.jobs[job_id]["state"] == "needs_attention"
    assert content._read_json(manager.job_dir / (job_id + ".json"))["state"] == "needs_attention"
    result = await manager.process({"action": "draft", "token": token})
    assert result["state"] == "needs_attention" and len(manager.jobs) == 1


@pytest.mark.asyncio
async def test_restart_does_not_repeat_in_progress_side_effect(manager, content):
    job_id = "a" * 32
    job = {"job_id": job_id, "action": "draft", "release_id": "ep00", "state": "in_progress", "phase": "保存草稿", "message": "未确认", "updated_at": content.utc_now()}
    manager._save_job(job)
    resumed = content.ContentManager(manager.browser, asyncio.Lock())
    assert resumed.jobs[job_id]["state"] == "needs_attention"
    assert resumed.tasks == {}


@pytest.mark.asyncio
async def test_empty_metrics_are_not_reported_as_zero(manager):
    result = await manager.process({"action": "metrics"})
    assert result["metrics"]["fields"] == []
    assert "不能据此认为数值为零" in result["message"]
    assert result["metrics"]["source"].startswith("https://creator.douyin.com/")


@pytest.mark.asyncio
async def test_prepare_timeout_does_not_leave_a_plan(manager, content, monkeypatch):
    async def slow(request):
        await asyncio.sleep(1)

    monkeypatch.setattr(manager, "_prepare", slow)
    monkeypatch.setattr(content, "PAGE_OPERATION_TIMEOUT", .001)
    result = await manager.process({"action": "prepare", "release_id": "ep00"})
    assert result["state"] == "page_error"
    assert list(manager.plan_dir.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("visible,expected", [(False, False), (True, True)])
async def test_ai_gate_requires_visible_exact_control(manager, visible, expected):
    class Target:
        def __init__(self, present):
            self.present = present

        async def count(self):
            return int(self.present)

        async def is_visible(self):
            return visible

        async def is_checked(self):
            return True

    page = SimpleNamespace(get_by_role=lambda role, **kwargs: Target(role == "checkbox"))
    assert await manager._ai_is_selected(page) is expected


def test_rpc_envelope_keeps_legacy_login_protocol(content, monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "ops/douyin-login"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("dy_service_content_test", directory / "service.py")
    service = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, service)
    spec.loader.exec_module(service)
    assert service.parse_request(b'{"action":"status"}\n') == "status"
    payload = {"action": "content", "request": {"action": "prepare", "release_id": "ep00"}}
    assert service.parse_request(json.dumps(payload).encode()) == payload["request"]
    with pytest.raises(service.ProtocolError):
        service.parse_request(b'{"action":"content","request":{"action":"publish","confirmed":true}}')
