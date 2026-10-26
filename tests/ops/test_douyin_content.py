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


@pytest.mark.parametrize("payload", [
    {"action": "cover_import_saved", "release_id": "ep00", "image_base64": "AAAA", "image_id": "0" * 32},
    {"action": "cover_pair", "release_id": "ep00", "landscape_cover_id": "0" * 64},
    {"action": "cover_pair", "release_id": "../ep00", "landscape_cover_id": "0" * 64, "portrait_cover_id": "1" * 64},
    {"action": "cover_pair", "release_id": "ep00", "landscape_cover_id": "x" * 64, "portrait_cover_id": "1" * 64},
    {"action": "cover_pair", "release_id": "ep00", "landscape_cover_id": "0" * 64, "portrait_cover_id": "1" * 64, "from_release_id": "../other"},
    {"action": "cover_pair", "release_id": "ep00", "landscape_cover_id": "0" * 64, "portrait_cover_id": "1" * 64, "cover_id": "2" * 64},
    {"action": "cover_import_saved", "release_id": "ep00", "image_base64": ""},
    {"action": "cover_import_saved", "release_id": "ep00", "image_base64": "a" * (12 * 1024 * 1024 + 1)},
])
def test_rejects_invalid_saved_cover_internal_protocol(content, payload):
    with pytest.raises(ValueError):
        content.validate_request(payload)


def test_accepts_closed_saved_cover_internal_protocol(content):
    imported = {
        "action": "cover_import_saved",
        "release_id": "ep00",
        "image_base64": "aGVsbG8=",
    }
    paired = {
        "action": "cover_pair",
        "release_id": "ep00",
        "landscape_cover_id": "a" * 64,
        "portrait_cover_id": "b" * 64,
        "from_release_id": "ep01",
    }
    assert content.validate_request(imported) == imported
    assert content.validate_request(paired) == paired


@pytest.mark.asyncio
async def test_saved_cover_internal_actions_route_to_single_image_import_and_pair(manager):
    calls = []

    def import_image(release_id, image, *, source=None):
        calls.append(("import", release_id, image, source))
        return {"cover_id": "c" * 64}

    def pair(release_id, landscape_cover_id, portrait_cover_id, *, from_release_id=None):
        calls.append(("pair", release_id, landscape_cover_id, portrait_cover_id, from_release_id))
        return {"cover_id": "d" * 64}

    manager.covers = SimpleNamespace(import_image=import_image, pair=pair)
    imported = await manager.process({
        "action": "cover_import_saved",
        "release_id": "ep00",
        "image_base64": "c291cmNlLWltYWdl",
    })
    paired = await manager.process({
        "action": "cover_pair",
        "release_id": "ep00",
        "landscape_cover_id": "a" * 64,
        "portrait_cover_id": "b" * 64,
        "from_release_id": "ep01",
    })

    assert imported["state"] == "ready" and imported["cover"]["cover_id"] == "c" * 64
    assert paired["state"] == "ready" and paired["cover"]["cover_id"] == "d" * 64
    assert calls == [
        ("import", "ep00", b"source-image", "saved_image"),
        ("pair", "ep00", "a" * 64, "b" * 64, "ep01"),
    ]


@pytest.mark.asyncio
async def test_saved_cover_import_uses_strict_base64(manager):
    manager.covers = SimpleNamespace(import_image=lambda *_args, **_kwargs: pytest.fail("不应导入无效图片"))
    result = await manager.process({
        "action": "cover_import_saved",
        "release_id": "ep00",
        "image_base64": "%%%not-base64%%%",
    })
    assert result["state"] == "needs_attention"


@pytest.fixture
def manager(content, tmp_path, monkeypatch):
    release = {"release_id": "ep00", "title": "序栞", "description": "星栞书库", "ai_generated": True,
               "video_sha256": "a" * 64, "video_path": tmp_path / "video.mp4"}
    store = SimpleNamespace(
        load=lambda release_id: dict(release),
        load_metadata=lambda release_id: dict(release),
        list_releases=lambda: [{"release_id": "ep00"}],
        list_metadata=lambda: [{"release_id": "ep00"}],
    )
    monkeypatch.setattr(content, "ReleaseStore", lambda data_dir: store)
    browser = SimpleNamespace(config=SimpleNamespace(data_dir=tmp_path, expected_account="expected"), _context=None)
    result = content.ContentManager(browser, asyncio.Lock())

    class Page:
        def __init__(self):
            self.url = "https://creator.douyin.com/creator-micro/home"

        async def goto(self, *args, **kwargs):
            self.url = args[0]

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


async def _checkpoint_editor(manager, content, monkeypatch):
    manager.covers = SimpleNamespace(load=lambda *_: {"cover_sha256": "d" * 64})
    result = await manager.process({"action": "prepare", "release_id": "ep00", "cover_id": "c" * 64})
    token = result["plan"]["token"]
    plan, release = manager._plan(token)
    markers = {"upload": "original-upload", "editor": None}

    async def evaluate(script, argument=None):
        if "__hermesUploadProof" in script:
            return markers["upload"]
        if "__hermesEditorProof = marker" in script:
            markers["editor"] = argument
        return markers["editor"]

    page = SimpleNamespace(url=content.UPLOAD_URL, is_closed=lambda: False, evaluate=evaluate)
    manager.browser._context = SimpleNamespace(pages=[page])
    manager._uploads[token] = {
        "page": page, "context": manager.browser._context, "marker": markers["upload"],
        "video_source": "blob:original-video", "fingerprint": plan["fingerprint"],
        "video_sha256": plan["video_sha256"], "deadline": time.monotonic() + 900,
    }
    for method in ["_fill_metadata", "_ai_declaration", "_dismiss_preview_tip", "_verify_metadata"]:
        monkeypatch.setattr(manager, method, AsyncMock())
    monkeypatch.setattr(manager, "_video_source", AsyncMock(return_value="blob:original-video"))
    monkeypatch.setattr(manager, "_upload_failed", AsyncMock(return_value=False))
    monkeypatch.setattr(content, "apply_cover", AsyncMock(return_value={"verified": True}))
    monkeypatch.setattr(content, "apply_settings", AsyncMock())
    job = {"job_id": "b" * 32, "action": "stage", "token": token, "release_id": "ep00",
           "fingerprint": plan["fingerprint"], "state": "in_progress", "phase": "编辑核验", "message": "处理中",
           "ai_declaration_verified": True}
    manager._save_job(job)
    return token, plan, release, page, job, markers


@pytest.mark.asyncio
async def test_post_upload_edit_failure_resumes_original_job_without_second_transfer(manager, content, monkeypatch):
    token, plan, release, page, job, _ = await _checkpoint_editor(manager, content, monkeypatch)
    transfer = AsyncMock(return_value=page)
    monkeypatch.setattr(manager, "_upload_video", transfer)
    monkeypatch.setattr(content, "apply_settings", AsyncMock(side_effect=[ValueError("页面控件暂时未加载"), None]))
    await manager._run(job, plan, release)
    assert job["state"] == "needs_attention" and job["recovery"] == {"action": "resume_stage"}
    assert 0 < manager.editor_lease_remaining() <= 900
    response = await manager.process({"action": "resume_stage", "token": token})
    assert response["job"]["job_id"] == job["job_id"]
    duplicate = await manager.process({"action": "resume_stage", "token": token})
    assert duplicate["job"]["job_id"] == job["job_id"] and len(manager.tasks) == 1
    await asyncio.gather(*list(manager.tasks.values()))
    assert job["state"] == "editor_ready" and len(manager.jobs) == 1
    transfer.assert_awaited_once()
    assert token not in manager._uploads and token in manager._staged
    assert not job.get("commit_attempted")


@pytest.mark.asyncio
async def test_completed_upload_gets_full_preview_lease_after_prepare_expiry(manager, content, monkeypatch):
    token, plan, release, page, job, _ = await _checkpoint_editor(manager, content, monkeypatch)
    plan["expires_unix"] = time.time() - 1
    content._write_json(manager.plan_dir / (token + ".json"), plan)
    job.update(state="needs_attention")
    manager._save_job(job)
    transfer = AsyncMock(side_effect=AssertionError("不能再次上传"))
    monkeypatch.setattr(manager, "_upload_video", transfer)
    clock = SimpleNamespace(time=lambda: plan["expires_unix"] + 2, monotonic=lambda: 5000)
    monkeypatch.setattr(content, "time", clock)
    manager._uploads[token]["deadline"] = 5900
    response = await manager.process({"action": "resume_stage", "token": token})
    assert response["state"] == "in_progress"
    await asyncio.gather(*list(manager.tasks.values()))
    assert job["state"] == "editor_ready" and manager._staged[token]["deadline"] == 5900
    assert manager._plan(token, allow_live=True)[0]["token"] == token
    with pytest.raises(ValueError, match="过期"):
        manager._plan(token)
    clock.monotonic = lambda: 5901
    with pytest.raises(ValueError, match="过期"):
        manager._plan(token, allow_live=True)
    transfer.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["page", "context", "marker", "video", "fingerprint", "hash", "account", "expired"])
async def test_resume_rejects_changed_upload_identity_without_falling_back_to_upload(manager, content, monkeypatch, change):
    token, plan, release, page, job, markers = await _checkpoint_editor(manager, content, monkeypatch)
    job.update(state="needs_attention")
    manager._save_job(job)
    if change == "page":
        page.is_closed = lambda: True
    elif change == "context":
        manager.browser._context = SimpleNamespace(pages=[page])
    elif change == "marker":
        markers["upload"] = "other-document"
    elif change == "video":
        manager._video_source.return_value = "blob:other-video"
    elif change == "fingerprint":
        manager._uploads[token]["fingerprint"] = "f" * 64
    elif change == "hash":
        manager._uploads[token]["video_sha256"] = "f" * 64
    elif change == "account":
        manager.browser.config.expected_account = "other-account"
    else:
        manager._uploads[token]["deadline"] = 0
    transfer = AsyncMock(side_effect=AssertionError("不能再次上传"))
    monkeypatch.setattr(manager, "_upload_video", transfer)
    result = await manager.process({"action": "resume_stage", "token": token})
    if manager.tasks:
        await asyncio.gather(*list(manager.tasks.values()))
    assert result["state"] in {"in_progress", "needs_attention"}
    assert job["state"] == "needs_attention"
    assert not manager._staged and not job.get("commit_attempted")
    transfer.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_cannot_bypass_unknown_publish_or_restart(manager, content, monkeypatch):
    token, plan, _, _, job, _ = await _checkpoint_editor(manager, content, monkeypatch)
    job.update(state="needs_attention")
    manager._save_job(job)
    other = {**job, "job_id": "e" * 32, "action": "publish", "commit_attempted": True}
    manager._save_job(other)
    response = await manager.process({"action": "resume_stage", "token": token})
    assert response["state"] == "needs_attention" and "结果未知" in response["message"]
    assert not manager.tasks
    restarted = content.ContentManager(manager.browser, asyncio.Lock())
    assert not restarted._uploads and not restarted._staged
    response = await restarted.process({"action": "resume_stage", "token": token})
    assert response["state"] == "needs_attention" and not restarted.tasks


@pytest.mark.asyncio
async def test_cancelled_stage_drops_checkpoint_and_does_not_offer_resume(manager, content, monkeypatch):
    token, plan, release, _, job, _ = await _checkpoint_editor(manager, content, monkeypatch)
    monkeypatch.setattr(manager, "_execute", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await manager._run(job, plan, release)
    assert token not in manager._uploads
    assert job["recovery"] != {"action": "resume_stage"}


@pytest.mark.asyncio
async def test_resume_protocol_crosses_plugin_validation_and_manager_without_upload(manager, content, monkeypatch):
    token, plan, _, page, job, _ = await _checkpoint_editor(manager, content, monkeypatch)
    job.update(state="needs_attention", recovery={"action": "resume_stage"})
    manager._save_job(job)
    path = Path(__file__).resolve().parents[2] / "ops/douyin-plugin/__init__.py"
    spec = importlib.util.spec_from_file_location("dy_resume_pipeline", path)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    monkeypatch.setattr(plugin, "_authorized", lambda: True)
    requests = []

    async def transport(payload):
        requests.append(payload)
        validated = content.validate_request(payload)
        response = await manager.process(validated)
        return plugin._validate_content_response(response, action=payload["action"])

    monkeypatch.setattr(plugin, "_request_content", transport)
    transfer = AsyncMock(side_effect=AssertionError("恢复不得上传"))
    monkeypatch.setattr(manager, "_upload_video", transfer)
    response = json.loads(await plugin.handle_content({"action": "resume_stage", "plan_id": token}))
    assert response["state"] == "in_progress"
    assert requests == [{"action": "resume_stage", "token": token}]
    await asyncio.gather(*list(manager.tasks.values()))
    response = json.loads(await plugin.handle_content({"action": "job", "job_id": job["job_id"]}))
    assert response["state"] == "editor_ready" and page is manager._staged[token]["page"]
    assert len(manager.jobs) == 1 and not job.get("commit_attempted")
    transfer.assert_not_awaited()


@pytest.mark.asyncio
async def test_sms_wait_uses_publish_budget_and_does_not_block_other_coroutines(manager, content, monkeypatch):
    entered = asyncio.Event()
    answer = asyncio.Event()
    calls = []

    async def success_wait(*, state, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError()
        entered.set()
        await answer.wait()

    success = SimpleNamespace(wait_for=success_wait)
    page = SimpleNamespace(get_by_text=lambda *_a, **_k: SimpleNamespace(first=success))
    button = SimpleNamespace(is_enabled=AsyncMock(return_value=True), click=AsyncMock())
    monkeypatch.setattr(manager, "_verified_stage", AsyncMock(return_value=page))
    monkeypatch.setattr(manager, "_dismiss_preview_tip", AsyncMock())
    monkeypatch.setattr(manager, "_button", AsyncMock(return_value=button))
    monkeypatch.setattr(manager, "_ui", AsyncMock(return_value={"text_tail": "接收短信验证码 为确保是本人操作抖音账号"}))
    monkeypatch.setattr(content, "JOB_TIMEOUT", .001)
    monkeypatch.setattr(content, "PUBLISH_TIMEOUT", 1)
    job = {"job_id": "a" * 32, "action": "publish", "release_id": "ep00", "state": "in_progress", "phase": "发布"}

    async def execute(current, plan, release):
        await manager._publish(page, current, plan)

    monkeypatch.setattr(manager, "_execute", execute)
    task = asyncio.create_task(manager._run(job, {"token": "a" * 32}, {}))
    await asyncio.wait_for(entered.wait(), 1)
    await asyncio.sleep(.01)
    assert manager.browser_lock.locked() and job["state"] == "in_progress"
    assert job["verification_required"] == "sms"
    answer.set()
    await task
    assert not manager.browser_lock.locked() and job["state"] == "published"
    button.click.assert_awaited_once()
    assert calls == [30000, 1800000]


def _operator_resolution(content, job):
    return {"outcome": "not_listed_at_check", "release_id": job["release_id"], "fingerprint": job["fingerprint"],
            "checked_at": content.utc_now(), "source": content.MANAGE_URL, "owner_authorization_ref": "fixture:owner-retry"}


@pytest.mark.asyncio
async def test_operator_resolution_unblocks_new_attempt_without_reusing_unknown_job(manager, content, monkeypatch):
    manager.covers = SimpleNamespace(load=lambda *_: {"cover_sha256": "d" * 64})
    prepared = await manager.process({"action": "prepare", "release_id": "ep00", "cover_id": "c" * 64})
    token = prepared["plan"]["token"]
    plan, _ = manager._plan(token)
    old = {"job_id": "c" * 32, "action": "publish", "release_id": "ep00", "state": "needs_attention",
           "phase": "发布短信结果未知", "message": "待核查", "fingerprint": plan["fingerprint"], "token": "b" * 32,
           "commit_attempted": True, "recovery": {"action": "inspect_result"}}
    manager._save_job(old)
    old["operator_resolution"] = _operator_resolution(content, old)
    manager._save_job(old)
    response = manager._job_response(old)
    assert response["recovery"] == {"action": "prepare"}
    path = Path(__file__).resolve().parents[2] / "ops/douyin-plugin/__init__.py"
    spec = importlib.util.spec_from_file_location("dy_operator_resolution_contract", path)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    assert plugin._validate_content_response(response, action="job")["recovery"] == {"action": "prepare"}
    assert old["state"] == "needs_attention" and old["commit_attempted"] is True
    denied = await manager.process({"action": "publish", "token": token})
    assert denied["state"] == "needs_attention" and "先stage" in denied["message"]
    manager._staged[token] = {"deadline": time.monotonic() + 100}
    invoked = []

    async def simulated_run(job, *_):
        invoked.append(job["job_id"])
        job.update(state="needs_attention", phase="隔离测试未发布", message="仅检查调度")
        manager._save_job(job)

    monkeypatch.setattr(manager, "_run", simulated_run)
    new = await manager.process({"action": "publish", "token": token})
    await asyncio.gather(*list(manager.tasks.values()))
    assert new["job"]["job_id"] != old["job_id"] and len(invoked) == 1
    assert len(manager.jobs) == 2 and old["state"] == "needs_attention"
    # 新尝试若再次结果未知，旧运维结论不能替新尝试解除防重。
    manager.jobs[new["job"]["job_id"]]["commit_attempted"] = True
    assert not content._has_operator_retry_resolution(manager.jobs[new["job"]["job_id"]])
    blocked = await manager.process({"action": "stage", "token": token})
    assert blocked["state"] == "needs_attention" and "结果未知" in blocked["message"]
    assert len(manager.jobs) == 2 and not manager.tasks


@pytest.mark.parametrize("field,value", [
    ("outcome", "published"), ("release_id", "ep01"), ("fingerprint", "different"),
    ("owner_authorization_ref", ""), ("source", "https://example.com"),
    ("checked_at", "2026-10-26T12:00:00"), ("checked_at", None),
])
def test_incomplete_or_mismatched_operator_resolution_does_not_unlock_publish(content, field, value):
    job = {"action": "publish", "state": "needs_attention", "commit_attempted": True,
           "release_id": "ep00", "fingerprint": "a" * 64}
    resolution = _operator_resolution(content, job)
    resolution[field] = value
    job["operator_resolution"] = resolution
    assert not content._has_operator_retry_resolution(job)
    with pytest.raises(ValueError):
        content.validate_request({"action": "stage", "token": "a" * 32, "operator_resolution": resolution})


def test_job_response_keeps_private_diagnostics_without_hiding_unknown_commit(manager):
    job = {"job_id": "a" * 32, "action": "publish", "release_id": "ep00",
           "state": "needs_attention", "phase": "结果待核实", "updated_at": "2026-10-26T04:17:17Z",
           "message": "已尝试提交，请核对实际结果，不要重投。", "commit_attempted": True,
           "recovery": {"action": "inspect_result"},
           "ui": {"text_tail": "网页诊断可能含 /private/path 或高熵长文本"}}
    result = manager._job_response(job)
    assert result["state"] == "needs_attention"
    assert result["recovery"] == {"action": "inspect_result"}
    assert "ui" not in result
    assert job["commit_attempted"] is True and "ui" in job


def test_unknown_job_response_survives_plugin_security_validation(manager):
    path = Path(__file__).resolve().parents[2] / "ops/douyin-plugin/__init__.py"
    spec = importlib.util.spec_from_file_location("job_response_plugin_contract", path)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    job = {"job_id": "a" * 32, "action": "publish", "release_id": "ep00",
           "state": "needs_attention", "phase": "结果待核实", "updated_at": "2026-10-26T04:17:17Z",
           "message": "已尝试提交，不要重投。", "commit_attempted": True,
           "recovery": {"action": "inspect_result"}, "ui": {"text_tail": "/private/path"}}
    response = manager._job_response(job)
    assert plugin._validate_content_response(response, action="job")["state"] == "needs_attention"
    with pytest.raises(ValueError):
        plugin._validate_content_response({**response, "ui": job["ui"]}, action="job")


def test_sms_challenge_reason_is_reported_without_private_phone_or_raw_ui(manager):
    job = {"job_id": "a" * 32, "action": "publish", "release_id": "ep00",
           "state": "needs_attention", "phase": "结果待核实", "updated_at": "2026-10-26T04:17:17Z",
           "message": "超时", "commit_attempted": True, "recovery": {"action": "inspect_result"},
           "ui": {"text_tail": "接收短信验证码 为确保是本人操作抖音账号 测试手机号177***50 获取验证码"}}
    result = manager._job_response(job)
    assert "短信验证" in result["message"]
    assert result["state"] == "needs_attention" and result["recovery"] == {"action": "inspect_result"}
    assert "177" not in json.dumps(result) and "ui" not in result
    assert job["message"] == "超时" and job["commit_attempted"] is True


def test_sms_challenge_still_matches_during_resend_countdown(content):
    assert content._sms_verification_visible({"text_tail": "接收短信验证码 为确保是本人操作抖音账号 59秒后重新发送 验证"})
    assert not content._sms_verification_visible({"text_tail": "作品简介中提到了短信验证码"})


@pytest.mark.asyncio
async def test_publish_keeps_same_page_waiting_for_user_sms_without_second_click(manager, monkeypatch):
    success = SimpleNamespace(wait_for=AsyncMock(side_effect=[TimeoutError(), None]))
    page = SimpleNamespace(get_by_text=lambda *_a, **_kw: SimpleNamespace(first=success))
    button = SimpleNamespace(is_enabled=AsyncMock(return_value=True), click=AsyncMock())
    monkeypatch.setattr(manager, "_verified_stage", AsyncMock(return_value=page))
    monkeypatch.setattr(manager, "_dismiss_preview_tip", AsyncMock())
    monkeypatch.setattr(manager, "_button", AsyncMock(return_value=button))
    monkeypatch.setattr(manager, "_ui", AsyncMock(return_value={
        "text_tail": "接收短信验证码 为确保是本人操作抖音账号 获取验证码"}))
    job = {"job_id": "a" * 32, "action": "publish", "release_id": "ep00", "state": "in_progress"}
    await manager._publish(page, job, {"token": "a" * 32})
    assert job["state"] == "published" and job["commit_attempted"] is True
    assert "verification_required" not in job
    button.click.assert_awaited_once()
    assert success.wait_for.await_args_list[0].kwargs["timeout"] == 30000
    assert success.wait_for.await_args_list[1].kwargs["timeout"] == 1800000


@pytest.mark.asyncio
async def test_library_routes_do_not_open_browser_or_create_publish_job(manager):
    from unittest.mock import Mock

    manager.covers = SimpleNamespace(
        catalog=Mock(return_value={"covers": [], "total": 0, "next_offset": None}),
        reuse=Mock(return_value={"release_id": "ep01", "cover_id": "a" * 64}),
    )
    result = await manager.process({"action": "cover_library", "release_id": "ep00", "offset": 0})
    assert result["state"] == "ready" and result["total"] == 0
    result = await manager.process({"action": "cover_reuse", "release_id": "ep01", "from_release_id": "ep00", "cover_id": "b" * 64})
    assert result["cover"]["release_id"] == "ep01"
    manager.covers.reuse.assert_called_once_with("ep01", "ep00", "b" * 64)
    assert not manager.jobs and manager.browser._context is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error,retries", [(TimeoutError(), 2), (ConnectionError(), 2), (ValueError("页面不匹配"), 1)])
async def test_navigation_retries_only_transient_errors_before_upload(manager, content, monkeypatch, error, retries):
    monkeypatch.setattr(content.asyncio, "sleep", AsyncMock())
    page = SimpleNamespace(
        url="https://creator.douyin.com/creator-micro/content/upload",
        goto=AsyncMock(side_effect=[error, None]),
    )
    if retries == 1:
        with pytest.raises(ValueError):
            await manager._navigate_entry(page, content.UPLOAD_URL)
    else:
        await manager._navigate_entry(page, content.UPLOAD_URL)
    assert page.goto.await_count == retries
    page.goto.reset_mock()
    with pytest.raises(ValueError, match="固定创作者入口"):
        await manager._navigate_entry(page, "https://example.com")
    page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_persistent_navigation_failure_has_only_two_attempts(manager, content, monkeypatch):
    monkeypatch.setattr(content.asyncio, "sleep", AsyncMock())
    page = SimpleNamespace(goto=AsyncMock(side_effect=TimeoutError()))
    with pytest.raises(TimeoutError):
        await manager._navigate_entry(page, content.HOME_URL)
    assert page.goto.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("redirect_at", ["navigation", "file_input_wait"])
async def test_upload_rejects_off_origin_redirect_before_reading_video(
    manager, content, monkeypatch, redirect_at
):
    uploaded = []
    page = SimpleNamespace(url="https://creator.douyin.com/creator-micro/home")

    async def navigate(url, **kwargs):
        page.url = (
            "https://outside.example/upload"
            if redirect_at == "navigation"
            else url
        )

    page.goto = AsyncMock(side_effect=navigate)

    class Upload:
        def __init__(self):
            self.first = self

        async def wait_for(self, **kwargs):
            if redirect_at == "file_input_wait":
                page.url = "https://outside.example/upload"

        async def count(self):
            return 1

        async def set_input_files(self, path):
            uploaded.append(path)

    upload = Upload()

    class TextField:
        async def wait_for(self, **kwargs):
            pass

        async def count(self):
            return 1

        async def fill(self, value):
            raise ValueError("测试在上传后停止")

    page.locator = lambda selector: (
        upload if 'input[type="file"]' in selector else TextField()
    )

    async def account_page():
        return page

    monkeypatch.setattr(manager, "_account_page", account_page)
    job = {"job_id": "d" * 32, "action": "stage", "release_id": "ep00", "phase": "排队"}
    plan = {
        "release_id": "ep00",
        "video_sha256": "a" * 64,
        "title": "测试标题",
        "description": "测试简介",
    }
    release = dict(manager.test_release)

    with pytest.raises(ValueError):
        await manager._execute(job, plan, release)

    assert uploaded == []


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
async def test_account_page_uses_extended_wait_without_relaxing_identity(manager, content, monkeypatch):
    page = SimpleNamespace()
    snapshot = {
        "has_creator_navigation": True,
        "expected_account_visible": True,
        "account_ids": ["expected"],
    }
    manager.browser._page = AsyncMock(return_value=page)
    manager.browser._wait_for_login_ui = AsyncMock(return_value=snapshot)
    manager.invalidate_editor = lambda: None
    monkeypatch.setattr(manager, "_navigate_entry", AsyncMock())
    monkeypatch.setitem(sys.modules, "service", SimpleNamespace(
        classify_page=lambda value, expected: "logged_in"
        if value["expected_account_visible"] and expected == "expected" else "unknown"
    ))

    result = await content.ContentManager._account_page(manager)

    assert result is page
    manager.browser._wait_for_login_ui.assert_awaited_once_with(
        page, wait_for_qr=False, timeout_seconds=content.ACCOUNT_WAIT_SECONDS
    )
    assert content.ACCOUNT_WAIT_SECONDS > 8


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


def test_large_video_budget_does_not_extend_editor_confirmation(content):
    assert content.PLAN_TTL == 3600
    assert content.JOB_TIMEOUT >= content.UPLOAD_TIMEOUT + 15 * 60
    assert content.UPLOAD_TIMEOUT == 3300
    assert content.EDITOR_LEASE_SECONDS == 900
    assert content.SMS_VERIFICATION_TIMEOUT == 1800
    assert content.PUBLISH_TIMEOUT > content.SMS_VERIFICATION_TIMEOUT + 30


@pytest.mark.asyncio
async def test_platform_upload_failure_is_detected_and_preserved(manager, content, monkeypatch):
    failure = SimpleNamespace(count=AsyncMock(return_value=1), is_visible=AsyncMock(return_value=True))
    page = SimpleNamespace(get_by_text=lambda *_args, **_kwargs: failure)
    assert await manager._upload_failed(page)

    async def execute(*_args):
        raise content.UploadFailedError("平台报告视频上传失败")

    monkeypatch.setattr(manager, "_execute", execute)
    job = {"job_id": "u" * 32, "action": "stage", "release_id": "ep00", "state": "in_progress", "phase": "等待视频处理"}
    await manager._run(job, {}, {})
    result = manager._job_response(job)
    assert result["state"] == "needs_attention"
    assert result["message"] == "平台报告视频上传失败"
    assert not job.get("commit_attempted")


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
async def test_restart_keeps_old_unknown_publish_with_more_than_1000_jobs(
    manager, content, monkeypatch
):
    old_plan = await manager.process(
        {"action": "prepare", "release_id": "ep00", "title": "旧文案"}
    )
    new_plan = await manager.process(
        {"action": "prepare", "release_id": "ep00", "title": "新文案"}
    )
    old_token = old_plan["plan"]["token"]
    new_token = new_plan["plan"]["token"]
    old, _release = manager._plan(old_token)
    new, _release = manager._plan(new_token)
    assert old["fingerprint"] != new["fingerprint"]

    unknown_id = "0" * 32
    manager._save_job({
        "job_id": unknown_id,
        "action": "publish",
        "release_id": "ep00",
        "state": "needs_attention",
        "phase": "发布结果待核查",
        "message": "不要重提",
        "fingerprint": old["fingerprint"],
        "token": old_token,
        "commit_attempted": True,
    })
    for number in range(1, 1001):
        job_id = f"{number:032x}"
        manager._save_job({
            "job_id": job_id,
            "action": "draft",
            "release_id": "ep00",
            "state": "draft_saved",
            "phase": "草稿已保存",
            "message": "已完成",
        })

    resumed = content.ContentManager(manager.browser, asyncio.Lock())
    assert unknown_id in resumed.jobs
    assert resumed.jobs[unknown_id]["state"] == "needs_attention"
    resumed._staged[new_token] = {"deadline": time.monotonic() + 100}

    async def idle_run(*_args):
        await asyncio.Event().wait()

    monkeypatch.setattr(resumed, "_run", idle_run)
    result = await resumed.process({"action": "publish", "token": new_token})

    assert result["state"] == "needs_attention"
    assert "结果未知" in result["message"]
    assert resumed.tasks == {}


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
