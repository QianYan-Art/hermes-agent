"""作品协议与持久任务边界；不连接真实抖音，不将模拟结果当作发布验收。"""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import time
from unittest.mock import AsyncMock

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
    {"action": "covers", "release_id": "ep00", "times": [10 ** 400]},
    {"action": "covers", "release_id": "ep00", "times": [float("nan")]},
    {"action": "covers", "release_id": "ep00", "times": [True]},
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
@pytest.mark.parametrize("state,action", [
    ("login_required", "login"), ("verification_required", "manual_verification"),
    ("account_mismatch", "check_account"), ("unknown", "check_status"),
])
async def test_prepare_returns_typed_account_recovery(manager, content, monkeypatch, state, action):
    async def failed():
        raise content.AccountStateError(state)
    monkeypatch.setattr(manager, "_account_page", failed)
    result = await manager.process({"action": "prepare", "release_id": "ep00"})
    assert result["state"] == state and result["ok"] is False
    assert result["recovery"] == {"action": action}
    assert not manager.jobs


@pytest.mark.asyncio
@pytest.mark.parametrize("committed", [False, True])
async def test_job_account_recovery_never_reopens_unknown_commit(manager, content, monkeypatch, committed):
    async def execute(*_):
        raise content.AccountStateError("login_required")
    monkeypatch.setattr(manager, "_execute", execute)
    job = {"job_id": "a" * 32, "action": "draft", "release_id": "ep00",
           "state": "in_progress", "phase": "测试", "message": "测试", "commit_attempted": committed}
    await manager._run(job, {}, {})
    result = manager._job_response(job)
    assert job["state"] == "needs_attention"
    assert result["state"] == ("needs_attention" if committed else "login_required")
    assert result["recovery"]["action"] == ("inspect_result" if committed else "login")


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
async def test_restart_invalidates_editor_proof(manager, content):
    job = {"job_id": "c" * 32, "action": "stage", "release_id": "ep00", "state": "editor_ready", "phase": "预览", "message": "待确认"}
    manager._save_job(job)
    resumed = content.ContentManager(manager.browser, asyncio.Lock())
    assert resumed.jobs[job["job_id"]]["state"] == "needs_attention"
    assert resumed._staged == {}


@pytest.mark.asyncio
async def test_stage_requires_chosen_cover_and_never_starts_without_it(manager):
    prepared = await manager.process({"action": "prepare", "release_id": "ep00"})
    result = await manager.process({"action": "stage", "token": prepared["plan"]["token"]})
    assert result["state"] == "needs_attention"
    assert manager.jobs == {}


@pytest.mark.asyncio
async def test_cover_and_settings_are_bound_to_fingerprint(manager, monkeypatch):
    monkeypatch.setattr(manager.covers, "load", lambda *_: {"cover_sha256": "b" * 64})
    first = await manager.process({"action": "prepare", "release_id": "ep00", "cover_id": "b" * 64})
    second = await manager.process({"action": "prepare", "release_id": "ep00", "cover_id": "c" * 64, "visibility": "private"})
    a, _ = manager._plan(first["plan"]["token"])
    b, _ = manager._plan(second["plan"]["token"])
    assert a["fingerprint"] != b["fingerprint"]
    assert b["settings"]["visibility"] == "private"
    monkeypatch.setattr(manager.covers, "load", lambda *_: {"cover_sha256": "d" * 64})
    with pytest.raises(ValueError, match="封面发生变化"):
        manager._plan(second["plan"]["token"])


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["expired", "context", "document", "video", "closed", "origin"])
async def test_publish_refuses_changed_staged_source_before_any_click(manager, monkeypatch, change):
    token = "a" * 32
    context = object()
    manager.browser._context = context
    page = SimpleNamespace(url="https://creator.douyin.com/creator-micro/content/post/video",
                           is_closed=lambda: change == "closed", evaluate=AsyncMock(return_value="marker"))
    manager._staged[token] = {"page": page, "context": context, "marker": "marker", "video_source": "source", "cover": {}, "deadline": time.monotonic() + 100}
    monkeypatch.setattr(manager, "_video_source", AsyncMock(return_value="other" if change == "video" else "source"))
    if change == "expired":
        manager._staged[token]["deadline"] = 0
    elif change == "context":
        manager.browser._context = object()
    elif change == "document":
        page.evaluate.return_value = "other"
    elif change == "origin":
        page.url = "https://example.org/creator-micro/content/post/video"
    with pytest.raises(ValueError):
        await manager._publish(None, {}, {"token": token})


def test_navigation_invalidates_ready_jobs_and_lease(manager):
    job = {"job_id": "d" * 32, "action": "stage", "release_id": "ep00", "state": "editor_ready", "phase": "预览", "message": "待确认"}
    manager._save_job(job)
    manager._staged["a" * 32] = {"deadline": time.monotonic() + 99999}
    assert manager.editor_lease_remaining() == 900
    manager.invalidate_editor()
    assert manager.editor_lease_remaining() == 0
    assert job["state"] == "needs_attention"


@pytest.mark.asyncio
async def test_stage_source_activates_video_tab_but_verification_never_recreates_it(manager):
    actions = []

    class Tab:
        def and_(self, _):
            return self

        async def count(self):
            return 1

        async def click(self):
            actions.append("只切视频预览")

    page = SimpleNamespace(url="https://creator.douyin.com/creator-micro/content/post/video",
                           get_by_text=lambda *_, **__: Tab(), locator=lambda *_: object(),
                           evaluate=AsyncMock(side_effect=[[], ["blob:owned-upload"]]))
    assert await manager._video_source(page, activate=True) == "blob:owned-upload"
    assert actions == ["只切视频预览"]
    page.evaluate = AsyncMock(return_value=[])
    with pytest.raises(ValueError, match="不恢复或猜测"):
        await manager._video_source(page)
    assert actions == ["只切视频预览"]


@pytest.mark.asyncio
async def test_multiple_visible_video_sources_are_never_guessed(manager):
    page = SimpleNamespace(url="https://creator.douyin.com/creator-micro/content/post/video",
                           evaluate=AsyncMock(return_value=["blob:one", "blob:two"]))
    with pytest.raises(ValueError, match="唯一确认"):
        await manager._video_source(page)


@pytest.mark.asyncio
async def test_unknown_publish_result_is_not_retried_even_after_restart(manager, content, monkeypatch):
    prepared = await manager.process({"action": "prepare", "release_id": "ep00"})
    token = prepared["plan"]["token"]
    manager._staged[token] = {"deadline": time.monotonic() + 100}
    attempts = []

    async def execute(job, *_):
        job["commit_attempted"] = True
        manager._save_job(job)
        attempts.append(job["job_id"])
        raise TimeoutError("模拟点击提交后未收到平台结果")

    monkeypatch.setattr(manager, "_execute", execute)
    first = await manager.process({"action": "publish", "token": token})
    await asyncio.gather(*list(manager.tasks.values()))
    again = await manager.process({"action": "publish", "token": token})
    assert first["job"]["job_id"] == again["job"]["job_id"]
    assert len(attempts) == 1 and again["state"] == "needs_attention"
    resumed = content.ContentManager(manager.browser, asyncio.Lock())
    again = await resumed.process({"action": "publish", "token": token})
    assert again["state"] == "needs_attention" and resumed.tasks == {}
    assert len(attempts) == 1 and len(resumed.jobs) == 1
    changed = await manager.process({"action": "prepare", "release_id": "ep00", "title": "修改后的文案"})
    changed_token = changed["plan"]["token"]
    manager._staged[changed_token] = {"deadline": time.monotonic() + 100}
    result = await manager.process({"action": "publish", "token": changed_token})
    assert result["state"] == "needs_attention" and len(manager.jobs) == 1
    assert "换文案" in result["message"]


@pytest.mark.asyncio
async def test_staged_draft_never_uploads_again_when_source_check_fails(manager, monkeypatch):
    prepared = await manager.process({"action": "prepare", "release_id": "ep00"})
    token = prepared["plan"]["token"]
    plan, release = manager._plan(token)
    manager._staged[token] = {"deadline": 0}
    monkeypatch.setattr(manager, "_verified_stage", AsyncMock(side_effect=ValueError("视频源已变化")))
    navigation = AsyncMock()
    monkeypatch.setattr(manager, "_account_page", navigation)
    with pytest.raises(ValueError):
        await manager._execute({"action": "draft"}, plan, release)
    navigation.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_attempted", [False, True])
async def test_only_root_authorized_precommit_draft_can_resume(manager, content, monkeypatch, commit_attempted):
    prepared = await manager.process({"action": "prepare", "release_id": "ep00"})
    token = prepared["plan"]["token"]
    plan, release = manager._plan(token)
    job_id = "b" * 32
    job = {"job_id": job_id, "action": "draft", "release_id": "ep00", "state": "needs_attention", "phase": "未确认",
           "message": "失败", "updated_at": content.utc_now(), "fingerprint": plan["fingerprint"],
           "commit_attempted": commit_attempted, "root_resume_authorized": True}
    manager._save_job(job)
    invoked = []

    async def execute(current_job, *args):
        invoked.append(current_job["job_id"])
        current_job.update(state="draft_saved", phase="草稿已保存", message="模拟确认")
        manager._save_job(current_job)

    monkeypatch.setattr(manager, "_execute", execute)
    result = await manager.process({"action": "draft", "token": token})
    assert result["job"]["job_id"] == job_id
    if commit_attempted:
        assert invoked == [] and result["state"] == "needs_attention"
    else:
        await asyncio.gather(*list(manager.tasks.values()))
        assert invoked == [job_id] and len(manager.jobs) == 1
        assert "root_resume_authorized" not in manager.jobs[job_id]


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

        def filter(self, **kwargs):
            return self

        async def evaluate(self, script):
            return False

        def locator(self, selector):
            return Target(False)

    page = SimpleNamespace(get_by_role=lambda role, **kwargs: Target(role == "checkbox"), locator=lambda selector: Target(False), evaluate=AsyncMock(return_value=False))
    assert await manager._ai_is_selected(page) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("too_broad", [False, True])
async def test_ai_modal_requires_scoped_confirmation(manager, monkeypatch, too_broad):
    events = []

    class Target:
        async def count(self):
            return 1

        async def is_visible(self):
            return True

        async def click(self):
            events.append("点击")

        async def wait_for(self, **kwargs):
            events.append(kwargs["state"])

        def locator(self, selector):
            assert selector == ".."
            return self

        def filter(self, **kwargs):
            return self

        def get_by_role(self, role, **kwargs):
            assert role == "button" and kwargs["name"] in ("确定", "取消")
            return self

        def and_(self, other):
            return self

        async def evaluate(self, script):
            return too_broad

    selected = iter((False, True))

    async def checked(page):
        return next(selected)

    class Checkbox:
        async def count(self):
            return 1

        async def is_visible(self):
            return True

        async def check(self):
            events.append("选择")

    monkeypatch.setattr(manager, "_ai_is_selected", checked)
    page = SimpleNamespace(get_by_text=lambda *args, **kwargs: Target(),
                           get_by_role=lambda *args, **kwargs: Checkbox(), locator=lambda selector: Target())
    if too_broad:
        with pytest.raises(ValueError, match="无法唯一定位"):
            await manager._ai_declaration(page)
        assert events == ["点击"]
    else:
        await manager._ai_declaration(page)
        assert events == ["点击", "点击", "hidden", "visible"]


@pytest.mark.asyncio
@pytest.mark.parametrize("actual,valid", [("星栞书库\u200b", True), ("其他文案", False), (" 星栞书库", False), ("星栞书库 ", False)])
async def test_saved_metadata_allows_only_editor_zero_width_separator(manager, actual, valid):
    class Field:
        async def wait_for(self, **kwargs):
            pass

        async def count(self):
            return 1

        async def input_value(self):
            return "序栞"

        async def evaluate(self, script):
            return False

        async def inner_text(self):
            return actual

    page = SimpleNamespace(locator=lambda selector: Field())
    plan = {"title": "序栞", "description": "星栞书库"}
    if valid:
        await manager._verify_metadata(page, plan)
    else:
        with pytest.raises(ValueError, match="简介发生变化"):
            await manager._verify_metadata(page, plan)


@pytest.mark.asyncio
async def test_draft_banner_requires_banner_and_allowed_origin(manager, content):
    events = []

    class Target:
        async def wait_for(self, **kwargs):
            pass

        async def count(self):
            return 1

        async def is_visible(self):
            return True

        async def click(self):
            events.append("不应消费暂存")
    page = SimpleNamespace(url=content.UPLOAD_URL, get_by_text=lambda *a, **k: Target())
    await manager._verify_draft_banner(page)
    assert events == []
    page.url = "https://example.com/creator-micro/content/upload"
    with pytest.raises(ValueError, match="允许的草稿入口"):
        await manager._verify_draft_banner(page)
    assert events == []


@pytest.mark.asyncio
async def test_draft_banner_check_does_not_consume_saved_slot(manager, content):
    clicks = []

    class Target:
        async def wait_for(self, **_):
            pass

        async def count(self):
            return 1

        async def is_visible(self):
            return True

        async def click(self):
            clicks.append("不应点击继续编辑")

    page = SimpleNamespace(url=content.UPLOAD_URL, get_by_text=lambda *_, **__: Target())
    await manager._verify_draft_banner(page)
    assert clicks == []


@pytest.mark.asyncio
async def test_browser_slot_without_video_identity_cannot_publish(manager, content):
    plan = {"fingerprint": "test"}
    previous = {"job_id": "a" * 32, "fingerprint": "test", "state": "draft_saved",
                "resume_mode": "browser_slot", "editor_url": content.UPLOAD_URL}
    manager.jobs[previous["job_id"]] = previous
    with pytest.raises(ValueError, match="可唯一定位"):
        await manager._publish(object(), {}, plan)


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
    with pytest.raises(service.ProtocolError):
        service.parse_request(json.dumps({"action": "content", "request": {"action": "covers", "release_id": "ep00", "times": [10 ** 400]}}).encode())
