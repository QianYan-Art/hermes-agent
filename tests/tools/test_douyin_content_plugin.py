"""抖音内容工具的RPC协议和发布确认门禁。"""

import asyncio
import base64
import importlib.util
import io
import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("douyin_content_plugin_test", ROOT / "ops/douyin-plugin/__init__.py")
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)

TOKEN = "a" * 32
OTHER_TOKEN = "b" * 32


@pytest.mark.asyncio
@pytest.mark.parametrize("action,expected", [("list", 2), ("job", 2), ("prepare", 1), ("stage", 1), ("resume_stage", 1), ("draft", 1), ("publish", 1)])
async def test_transport_retry_never_replays_mutating_content_requests(monkeypatch, action, expected):
    from unittest.mock import AsyncMock
    request = AsyncMock(side_effect=[OSError("连接暂断"), {"ok": True}])
    monkeypatch.setattr(plugin, "_request_content_once", request)
    monkeypatch.setattr(plugin.asyncio, "sleep", AsyncMock())
    if expected == 1:
        with pytest.raises(OSError):
            await plugin._request_content({"action": action})
    else:
        assert await plugin._request_content({"action": action}) == {"ok": True}
    assert request.await_count == expected


@pytest.mark.asyncio
async def test_invalid_transport_response_is_not_retried(monkeypatch):
    from unittest.mock import AsyncMock
    request = AsyncMock(side_effect=ValueError("非法响应"))
    monkeypatch.setattr(plugin, "_request_content_once", request)
    with pytest.raises(ValueError):
        await plugin._request_content({"action": "job"})
    assert request.await_count == 1


@pytest.mark.asyncio
async def test_fixture_login_recovery_pipeline_attaches_qr_without_model_echo(tmp_path, monkeypatch, owner_context):
    import hermes_constants
    from gateway import run
    from gateway.platforms import base
    image_module = pytest.importorskip("PIL.Image")
    data = io.BytesIO()
    image_module.new("RGB", (20, 20), "white").save(data, format="PNG")
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(run, "get_hermes_home", lambda: tmp_path)

    async def failed_prepare(request):
        return plugin._validate_content_response({"ok": False, "state": "login_required", "message": "需要扫码",
            "recovery": {"action": "login"}}, action=request["action"])

    async def login(action, *, recovery=False):
        assert action == "login" and recovery is True
        return {"ok": True, "state": "login_required", "message": "模拟二维码，不连接抖音",
                "qr_png_base64": base64.b64encode(data.getvalue()).decode()}

    monkeypatch.setattr(plugin, "_request_content", failed_prepare)
    monkeypatch.setattr(plugin, "_request", login)
    output = await plugin.handle_content({"action": "prepare", "release_id": "ep00", "cover_id": "a" * 64})
    result = json.loads(output)
    assert "qr_png_base64" not in output
    tag = result["login"]["media_tag"]
    messages = [{"role": "assistant", "tool_calls": [{"id": "prepare", "function": {"name": "douyin_content"}}]},
                {"role": "tool", "tool_call_id": "prepare", "content": output}]
    assert run._collect_auto_append_media_tags(messages) == ([tag], False)
    monkeypatch.setattr(base, "MEDIA_DELIVERY_SAFE_ROOTS", (tmp_path / "cache/douyin-login",))
    monkeypatch.setenv("HERMES_MEDIA_DELIVERY_STRICT", "1")
    monkeypatch.setenv("HERMES_MEDIA_TRUST_RECENT_FILES", "0")
    assert base.validate_media_delivery_path(tag[6:]) == str(Path(tag[6:]).resolve())


@pytest.mark.asyncio
@pytest.mark.parametrize("state,recovery", [("verification_required", "manual_verification"),
    ("account_mismatch", "check_account"), ("unknown", "check_status"), ("needs_attention", "inspect_result")])
async def test_non_login_failures_never_request_qr(monkeypatch, owner_context, state, recovery):
    async def result(_):
        return {"ok": False, "state": state, "message": "停止", "recovery": {"action": recovery}}
    async def forbidden(*_, **__):
        pytest.fail("此错误不得触发扫码恢复")
    monkeypatch.setattr(plugin, "_request_content", result)
    monkeypatch.setattr(plugin, "_request", forbidden)
    output = json.loads(await plugin.handle_content({"action": "job", "job_id": "a" * 32}))
    assert "login" not in output


@pytest.mark.asyncio
async def test_automatic_qr_is_never_attached_outside_owner_scope(monkeypatch, owner_context):
    async def result(_):
        return {"ok": False, "state": "login_required", "message": "停止", "recovery": {"action": "login"}}
    async def forbidden(*_, **__):
        pytest.fail("非本人会话不得自动获取二维码")
    monkeypatch.setattr(plugin, "_request_content", result)
    monkeypatch.setattr(plugin, "_owner_qq_dm_scope", lambda: None)
    monkeypatch.setattr(plugin, "_request", forbidden)
    assert "login" not in json.loads(await plugin.handle_content({"action": "job", "job_id": "a" * 32}))


@pytest.mark.parametrize("recovery", [{"action": []}, {"action": "shell"}, {"action": "login", "url": "x"}])
def test_recovery_response_cannot_expand_into_arbitrary_operations(recovery):
    with pytest.raises(ValueError):
        plugin._validate_content_response({"ok": False, "state": "login_required", "message": "停止", "recovery": recovery})


@pytest.mark.parametrize("times", [[], [10 ** 400], [float("inf")], [True]])
def test_cover_times_reject_huge_or_empty_values(times):
    with pytest.raises(ValueError):
        plugin._content_payload({"action": "covers", "release_id": "ep00", "times": times})


@pytest.fixture(autouse=True)
def clear_confirmation_state():
    with plugin._CONFIRMATION_LOCK:
        plugin._CONFIRMATIONS.clear()
        plugin._CONFIRMATION_NONCES.clear()
        plugin._USED_CONFIRMATION_TOKENS.clear()
    with plugin._INBOUND_IMAGE_LOCK:
        plugin._INBOUND_IMAGES.clear()
        plugin._INBOUND_IMAGE_NONCES.clear()
    yield
    with plugin._CONFIRMATION_LOCK:
        plugin._CONFIRMATIONS.clear()
        plugin._CONFIRMATION_NONCES.clear()
        plugin._USED_CONFIRMATION_TOKENS.clear()
    with plugin._INBOUND_IMAGE_LOCK:
        plugin._INBOUND_IMAGES.clear()
        plugin._INBOUND_IMAGE_NONCES.clear()


@pytest.fixture
def owner_context(monkeypatch):
    from gateway.session_context import clear_session_vars, set_session_vars

    owner = "owner"
    monkeypatch.setenv("DOUYIN_OWNER_QQ_USER_ID", owner)
    tokens = set_session_vars(
        platform="qqbot",
        user_id=owner,
        chat_id=owner,
        session_key=f"agent:main:qqbot:dm:{owner}",
        message_id="msg-1",
    )
    try:
        yield owner
    finally:
        clear_session_vars(tokens)


def _message(
    text,
    *,
    platform=None,
    user_id="owner",
    chat_id="owner",
    chat_type="dm",
    internal=False,
    nonce="msg-1",
    media_urls=None,
    media_types=None,
):
    from gateway.config import Platform
    from gateway.platforms.base import MessageEvent
    from gateway.session import SessionSource

    source = SessionSource(
        platform=platform or Platform.QQBOT,
        chat_id=chat_id,
        chat_type=chat_type,
        user_id=user_id,
    )
    return MessageEvent(
        text=text,
        source=source,
        message_id=nonce,
        internal=internal,
        media_urls=media_urls or [],
        media_types=media_types or [],
    )


def _success_response(state="published"):
    return {"ok": True, "state": state, "message": "已完成。"}


@pytest.mark.parametrize("args", [
    {"action": "list", "confirmed": True},
    {"action": "metrics", "release_id": "release-1"},
    {"action": "prepare", "release_id": "release-1", "url": "https://example.org"},
    {"action": "draft", "token": TOKEN, "confirmed": True},
    {"action": "job", "job_id": "0" * 32, "path": "C:\\secret"},
    {"action": "publish", "token": TOKEN, "confirmed": True},
    {"action": "stage", "token": TOKEN, "confirmed": True},
    {"action": "stage", "token": TOKEN, "cover_id": "f" * 64},
    {"action": "cover_import", "release_id": "release-1", "image_id": "0" * 32, "image_base64": "AAAA"},
    {"action": "cover_saved_sources"},
    {"action": "cover_saved_sources", "release_id": "../release"},
    {"action": "cover_import_saved", "release_id": "release-1", "image_id": "0" * 32, "image_base64": "AAAA"},
    {"action": "cover_pair", "release_id": "release-1", "landscape_cover_id": "a" * 64},
    {"action": "cover_pair", "release_id": "release-1", "landscape_cover_id": "a" * 64,
     "portrait_cover_id": "b" * 64, "unexpected": True},
    {"action": "cover_pair", "release_id": "release-1", "landscape_cover_id": "a" * 64,
     "portrait_cover_id": "b" * 64, "from_release_id": "../release"},
    {"action": "covers", "release_id": "release-1", "times": [float("inf")]},
    {"action": "covers", "release_id": "release-1", "times": [0, 1, 2, 3, 4, 5]},
    {"action": "prepare", "release_id": "release-1", "visibility": []},
    {"action": "prepare", "release_id": "release-1", "visibility": "all"},
    {"action": "prepare", "release_id": "release-1"},
    {"action": "prepare", "release_id": "release-1", "cover_id": "x" * 64},
    {"action": "prepare", "release_id": "release-1", "publish_at": "2026-10-23T12:00:00"},
])
def test_content_payload_rejects_fields_outside_action_protocol(args):
    with pytest.raises(ValueError):
        plugin._content_payload(args)


def test_content_payload_accepts_only_documented_action_shapes():
    assert plugin._content_payload({"action": "list"}) == "list"
    assert plugin._content_payload({"action": "metrics"}) == "metrics"
    assert plugin._content_payload({
        "action": "prepare",
        "release_id": "release-1",
        "title": "标题",
        "cover_id": "f" * 64,
    }) == "prepare"
    assert plugin._content_payload({"action": "draft", "token": TOKEN}) == "draft"
    assert plugin._content_payload({"action": "job", "job_id": "0" * 32}) == "job"
    assert plugin._content_payload({"action": "publish", "token": TOKEN}) == "publish"
    assert plugin._content_payload({"action": "covers", "release_id": "release-1", "times": [0, 1.25]}) == "covers"
    assert plugin._content_payload({"action": "cover_sources"}) == "cover_sources"
    assert plugin._content_payload({"action": "cover_import", "release_id": "release-1", "image_id": "0" * 32}) == "cover_import"
    assert plugin._content_payload({"action": "cover_saved_sources", "release_id": "release-1"}) == "cover_saved_sources"
    assert plugin._content_payload({"action": "cover_import_saved", "release_id": "release-1", "image_id": "0" * 32}) == "cover_import_saved"
    assert plugin._content_payload({
        "action": "cover_pair", "release_id": "release-1",
        "landscape_cover_id": "a" * 64, "portrait_cover_id": "b" * 64,
    }) == "cover_pair"
    assert plugin._content_payload({
        "action": "cover_pair", "release_id": "release-1",
        "landscape_cover_id": "a" * 64, "portrait_cover_id": "b" * 64,
        "from_release_id": "release-2",
    }) == "cover_pair"
    assert plugin._content_payload({
        "action": "prepare",
        "release_id": "release-1",
        "cover_id": "f" * 64,
        "visibility": "friends",
        "publish_at": "2026-10-23T12:00:00-07:00",
    }) == "prepare"
    assert plugin._content_payload({
        "action": "prepare",
        "release_id": "release-1",
        "cover_id": "f" * 64,
    }) == "prepare"
    assert plugin._content_payload({"action": "stage", "token": TOKEN}) == "stage"


def test_response_rejects_extra_roots_sensitive_fields_and_paths():
    valid = {
        "ok": True,
        "state": "ready",
        "message": "可用作品列表已读取。",
        "releases": [{"release_id": "release-1", "title": "标题"}],
        "metrics": {"source": "https://creator.douyin.com/creator-micro/home", "fields": []},
    }
    assert plugin._validate_content_response(valid) is valid

    for invalid in (
        {**valid, "cookie": "secret"},
        {"ok": True, "state": "ready", "message": "ok", "plan": {"cookie_value": "secret"}},
        {"ok": True, "state": "ready", "message": "ok", "ui": {"text_tail": "C:\\Users\\owner\\profile"}},
        {"ok": True, "state": "ready", "message": "ok", "ui": {"text_tail": "/var/lib/hermes/profile"}},
        {"ok": True, "state": "ready", "message": "ok", "unknown": True},
    ):
        with pytest.raises(ValueError):
            plugin._validate_content_response(invalid)


def test_content_rpc_uses_login_socket_and_single_line_content_envelope(monkeypatch):
    seen = {}

    class Reader:
        async def readline(self):
            return json.dumps({"ok": True, "state": "ready", "message": "就绪。"}, ensure_ascii=False).encode() + b"\n"

    class Writer:
        def write(self, data):
            seen["body"] = data

        async def drain(self):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def open_connection(path, *, limit):
        seen["path"] = path
        seen["limit"] = limit
        return Reader(), Writer()

    monkeypatch.setenv("DOUYIN_LOGIN_SOCKET", "/tmp/login.sock")
    monkeypatch.setattr(plugin.asyncio, "open_unix_connection", open_connection, raising=False)
    result = asyncio.run(plugin._request_content({"action": "list"}))

    assert result["state"] == "ready"
    assert seen["path"] == "/tmp/login.sock"
    assert seen["limit"] == plugin.MAX_CONTENT_RESPONSE
    assert json.loads(seen["body"]) == {"action": "content", "request": {"action": "list"}}
    assert seen["body"].endswith(b"\n")


def test_content_rpc_enforces_request_and_response_byte_limits(monkeypatch):
    async def unexpected_connection(*args, **kwargs):
        raise AssertionError("请求超限时不应连接服务")

    monkeypatch.setattr(plugin.asyncio, "open_unix_connection", unexpected_connection, raising=False)
    with pytest.raises(ValueError):
        asyncio.run(plugin._request_content({"action": "prepare", "release_id": "r", "description": "x" * (plugin.MAX_CONTENT_REQUEST + 1)}))

    class Reader:
        async def readline(self):
            return b" " * (plugin.MAX_CONTENT_RESPONSE + 1) + b"\n"

    class Writer:
        def write(self, data):
            return None

        async def drain(self):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def oversized_connection(*args, **kwargs):
        return Reader(), Writer()

    monkeypatch.setattr(plugin.asyncio, "open_unix_connection", oversized_connection, raising=False)
    with pytest.raises(ValueError):
        asyncio.run(plugin._request_content({"action": "list"}))


def test_registration_preserves_login_and_registers_content_hook():
    class RegisteredContextStub:
        def __init__(self):
            self.tools = {}
            self.hooks = []

        def register_tool(self, **kwargs):
            self.tools[kwargs["name"]] = kwargs

        def register_hook(self, hook_name, callback):
            self.hooks.append((hook_name, callback))

    ctx = RegisteredContextStub()
    plugin.register(ctx)

    assert {"douyin_login", "douyin_content", "douyin_verification"} <= set(ctx.tools)
    assert ctx.tools["douyin_verification"]["schema"]["parameters"]["properties"].keys() == {"job_id"}
    assert ctx.tools["douyin_login"]["toolset"] == "douyin"
    assert ctx.tools["douyin_login"]["schema"]["parameters"]["properties"]["action"]["enum"] == ["status", "login"]
    assert ctx.tools["douyin_content"]["toolset"] == "douyin"
    assert ctx.tools["douyin_content"]["schema"]["parameters"]["additionalProperties"] is False
    assert "confirmed" not in ctx.tools["douyin_content"]["schema"]["parameters"]["properties"]
    content_schema = ctx.tools["douyin_content"]["schema"]
    assert content_schema["parameters"]["properties"]["action"]["enum"] == [
        "list", "metrics", "covers", "cover_sources", "cover_import", "cover_saved_sources", "cover_import_saved",
        "cover_pair", "cover_library", "cover_reuse", "prepare", "stage", "resume_stage", "draft", "job", "publish"
    ]
    description = content_schema["description"]
    assert "横封面槽为4:3、竖封面槽为3:4" in description
    assert "9:16只是可能的素材版本" in description
    assert "cover_saved_sources" in description and "cover_import_saved" in description and "cover_pair" in description
    assert "15 分钟" in content_schema["description"]
    assert "job 查询不会导航" in content_schema["description"]
    assert "另一次 prepare" in content_schema["description"]
    assert ("pre_gateway_dispatch", plugin._observe_publish_confirmation) in ctx.hooks
    assert ("pre_gateway_enqueue", plugin._consume_verification_message) in ctx.hooks


@pytest.mark.parametrize("origin", [
    {"user_id": "other"},
    {"chat_id": "other"},
    {"chat_type": "group"},
    {"platform": "telegram"},
])
def test_confirmation_rejects_other_users_groups_and_platforms(owner_context, origin):
    from gateway.config import Platform

    options = dict(origin)
    platform = Platform(options.pop("platform", "qqbot"))
    event = _message(f"确认发布 {TOKEN}", platform=platform, **options)
    plugin._observe_publish_confirmation(event=event)
    assert not plugin._consume_publish_confirmation(TOKEN)


def test_internal_or_forged_confirmation_parameter_cannot_authorize(owner_context, monkeypatch):
    calls = []

    async def request(payload):
        calls.append(payload)
        return _success_response()

    monkeypatch.setattr(plugin, "_request_content", request)
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}", internal=True))
    output = asyncio.run(plugin.handle_content({"action": "publish", "token": TOKEN, "confirmed": True}))

    assert json.loads(output)["state"] == "needs_attention"
    assert calls == []


def test_expired_confirmation_is_rejected(owner_context, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(plugin.time, "monotonic", lambda: now[0])
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}"))
    now[0] += plugin._CONFIRMATION_TTL + 1
    assert not plugin._consume_publish_confirmation(TOKEN)


def test_confirmation_nonce_cannot_be_replayed_to_extend_expiry(owner_context, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(plugin.time, "monotonic", lambda: now[0])
    event = _message(f"确认发布 {TOKEN}", nonce="same-message")
    plugin._observe_publish_confirmation(event=event)
    now[0] += 100
    plugin._observe_publish_confirmation(event=event)
    now[0] += 21
    plugin._observe_publish_confirmation(event=event)
    assert not plugin._consume_publish_confirmation(TOKEN)


@pytest.mark.parametrize("text,nonce", [
    (f"确认发布 {TOKEN} ", "msg-1"),
    (f"请确认发布 {TOKEN}", "msg-1"),
    (f"确认发布 {TOKEN}", ""),
])
def test_confirmation_requires_exact_text_and_real_message_nonce(owner_context, text, nonce):
    plugin._observe_publish_confirmation(event=_message(text, nonce=nonce))
    assert not plugin._consume_publish_confirmation(TOKEN)


def test_confirmation_is_bound_to_token_and_consumed_once(owner_context, monkeypatch):
    calls = []

    async def request(payload):
        calls.append(payload)
        return _success_response()

    monkeypatch.setattr(plugin, "_request_content", request)
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}"))

    wrong = json.loads(asyncio.run(plugin.handle_content({"action": "publish", "token": OTHER_TOKEN})))
    first = json.loads(asyncio.run(plugin.handle_content({"action": "publish", "token": TOKEN})))
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}", nonce="second-message"))
    repeated = json.loads(asyncio.run(plugin.handle_content({"action": "publish", "token": TOKEN})))

    assert wrong["state"] == "needs_attention"
    assert first["state"] == "published"
    assert repeated["state"] == "needs_attention"
    assert calls == [{"action": "publish", "token": TOKEN}]


def test_cli_authorization_does_not_bypass_publish_confirmation(monkeypatch):
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv("DOUYIN_OWNER_QQ_USER_ID", "owner")
    tokens = set_session_vars(platform="", chat_id="", user_id="", session_key="")
    try:
        assert plugin._authorized()
        assert not plugin._consume_publish_confirmation(TOKEN)
    finally:
        clear_session_vars(tokens)


def test_only_original_user_confirmation_allows_publish_rpc(owner_context, monkeypatch):
    calls = []

    async def request(payload):
        calls.append(payload)
        return _success_response()

    monkeypatch.setattr(plugin, "_request_content", request)
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}"))
    output = asyncio.run(plugin.handle_content({"action": "publish", "token": TOKEN}))

    assert json.loads(output)["state"] == "published"
    assert calls == [{"action": "publish", "token": TOKEN}]


@pytest.mark.parametrize("action", ["stage", "draft"])
def test_plan_reference_survives_history_redaction(owner_context, monkeypatch, action):
    """模型侧稳定引用经过真实脱敏后仍可用于内部请求。"""
    from agent.redact import redact_sensitive_text

    calls = []

    async def request(payload):
        calls.append(payload)
        if payload["action"] == "prepare":
            return {"ok": True, "state": "ready", "message": "准备完成", "plan": {"token": TOKEN}}
        return _success_response("in_progress")

    monkeypatch.setattr(plugin, "_request_content", request)
    prepared = json.loads(asyncio.run(plugin.handle_content({
        "action": "prepare", "release_id": "ep00", "cover_id": "f" * 64,
    })))
    history = json.loads(redact_sensitive_text(json.dumps(prepared), force=True))
    assert "token" not in history["plan"]
    args = json.loads(redact_sensitive_text(json.dumps({
        "action": action, "plan_id": history["plan"]["plan_id"],
    }), force=True))
    assert json.loads(asyncio.run(plugin.handle_content(args)))["state"] == "in_progress"
    assert calls[-1] == {"action": action, "token": TOKEN}


def test_publish_uses_trusted_confirmation_without_model_copying_token(owner_context, monkeypatch):
    calls = []

    async def request(payload):
        calls.append(payload)
        return _success_response()

    monkeypatch.setattr(plugin, "_request_content", request)
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}"))
    first = json.loads(asyncio.run(plugin.handle_content({"action": "publish"})))
    repeated = json.loads(asyncio.run(plugin.handle_content({"action": "publish"})))
    assert first["state"] == "published"
    assert repeated["state"] == "needs_attention"
    assert calls == [{"action": "publish", "token": TOKEN}]


def test_concurrent_publish_uses_internal_service_protocol_once(owner_context, monkeypatch):
    """实际协议校验接收完整码；并发模型调用也只能消费一次授权。"""
    monkeypatch.syspath_prepend(str(ROOT / "ops/douyin-login"))
    spec = importlib.util.spec_from_file_location("douyin_confirmation_contract", ROOT / "ops/douyin-login/content.py")
    service = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, service)
    spec.loader.exec_module(service)
    calls = []

    async def request(payload):
        calls.append(service.validate_request(payload))
        await asyncio.sleep(0)
        raise OSError("模拟提交结果未知")

    async def invoke():
        return await asyncio.gather(*(plugin.handle_content({"action": "publish"}) for _ in range(2)))

    monkeypatch.setattr(plugin, "_request_content", request)
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}"))
    states = {json.loads(result)["state"] for result in asyncio.run(invoke())}
    assert states == {"unavailable", "needs_attention"}
    assert calls == [{"action": "publish", "token": TOKEN}]


@pytest.mark.parametrize("change", [{"message_id": "other-message"}, {"message_id": ""}, {"user_id": "other"}])
def test_publish_cannot_use_another_message_or_user_confirmation(owner_context, monkeypatch, change):
    from gateway.session_context import clear_session_vars, set_session_vars

    async def forbidden(_):
        pytest.fail("错误消息或用户不能进入发布服务")

    monkeypatch.setattr(plugin, "_request_content", forbidden)
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}"))
    reset = set_session_vars(**change)
    try:
        result = json.loads(asyncio.run(plugin.handle_content({"action": "publish"})))
        assert result["state"] == "needs_attention"
    finally:
        clear_session_vars(reset)


def test_new_user_message_revokes_pending_confirmation_and_replay_cannot_restore_it(owner_context, monkeypatch):
    async def forbidden(_):
        pytest.fail("后续消息已撤销旧确认，不能提交")

    monkeypatch.setattr(plugin, "_request_content", forbidden)
    confirmation = _message(f"确认发布 {TOKEN}")
    plugin._observe_publish_confirmation(event=confirmation)
    plugin._observe_publish_confirmation(event=_message("先别发布，修改一下", nonce="msg-2"))
    plugin._observe_publish_confirmation(event=confirmation)
    assert not plugin._consume_publish_confirmation(TOKEN)


def test_invalid_placeholder_can_be_corrected_without_consuming_confirmation(owner_context, monkeypatch):
    calls = []

    async def request(payload):
        calls.append(payload)
        return _success_response()

    monkeypatch.setattr(plugin, "_request_content", request)
    plugin._observe_publish_confirmation(event=_message(f"确认发布 {TOKEN}"))
    assert json.loads(asyncio.run(plugin.handle_content({"action": "publish", "token": "***"})))["state"] == "needs_attention"
    assert json.loads(asyncio.run(plugin.handle_content({"action": "publish"})))["state"] == "published"
    assert len(calls) == 1


@pytest.mark.parametrize("args", [
    {"action": "stage", "plan_id": TOKEN, "token": TOKEN},
    {"action": "draft", "plan_id": "***"},
    {"action": "publish", "plan_id": TOKEN, "token": OTHER_TOKEN},
])
def test_plan_reference_rejects_conflicting_or_masked_aliases(args):
    with pytest.raises(ValueError):
        plugin._content_payload(args)


def test_gateway_passes_actual_inbound_message_id_for_confirmation():
    from types import SimpleNamespace
    from gateway.run import GatewayRunner
    from gateway.session_context import clear_session_vars, get_session_env

    event = _message(f"确认发布 {TOKEN}", nonce="qq-actual-message")
    context = SimpleNamespace(source=event.source, session_key="agent:main:qqbot:dm:owner")
    reset = GatewayRunner._set_session_env(None, context, message_id=event.message_id)
    try:
        assert get_session_env("HERMES_SESSION_MESSAGE_ID") == "qq-actual-message"
    finally:
        clear_session_vars(reset)


@pytest.mark.parametrize("args", [
    {"action": "cover_library", "offset": True},
    {"action": "cover_library", "offset": -1},
    {"action": "cover_library", "release_id": "../ep00"},
    {"action": "cover_library", "path": "/tmp/a"},
    {"action": "cover_reuse", "release_id": "ep01", "from_release_id": "../ep00", "cover_id": "a" * 64},
    {"action": "cover_reuse", "release_id": "ep01", "from_release_id": "ep00", "cover_id": "***"},
])
def test_library_payload_rejects_untrusted_identifiers_and_paths(args):
    with pytest.raises(ValueError):
        plugin._content_payload(args)


@pytest.mark.parametrize("action", ["cover_library", "cover_reuse"])
def test_library_requires_actual_owner_dm_even_when_cli_is_allowed(monkeypatch, action):
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv("DOUYIN_OWNER_QQ_USER_ID", "owner")
    tokens = set_session_vars()
    args = {"action": action}
    if action == "cover_reuse":
        args.update(release_id="ep01", from_release_id="ep00", cover_id="a" * 64)
    try:
        assert json.loads(asyncio.run(plugin.handle_content(args)))["state"] == "unavailable"
    finally:
        clear_session_vars(tokens)


@pytest.mark.parametrize("action", ["cover_library", "cover_reuse"])
def test_owner_library_actions_reach_only_the_validated_service_protocol(owner_context, monkeypatch, action):
    monkeypatch.syspath_prepend(str(ROOT / "ops/douyin-login"))
    spec = importlib.util.spec_from_file_location("douyin_library_contract", ROOT / "ops/douyin-login/content.py")
    service = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, service)
    spec.loader.exec_module(service)
    calls = []

    async def request(payload):
        calls.append(service.validate_request(payload))
        return _success_response("ready")

    monkeypatch.setattr(plugin, "_request_content", request)
    args = {"action": action}
    if action == "cover_reuse":
        args.update(release_id="ep01", from_release_id="ep00", cover_id="a" * 64)
    result = json.loads(asyncio.run(plugin.handle_content(args)))
    assert result["state"] == "ready" and calls == [args]


@pytest.mark.parametrize("action", ["cover_library", "cover_reuse"])
def test_library_response_uses_existing_safe_preview_pipeline(monkeypatch, tmp_path, action):
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
    response = _cover_response()
    if action == "cover_library":
        response.update(total=1, next_offset=None)
    else:
        response["cover"] = response.pop("covers")[0]
        response["cover"]["source"] = "library_image"
        response["cover"].pop("time", None)
    sanitized = plugin._validate_content_response(response, action=action)
    assert "jpeg_base64" not in json.dumps(sanitized)
    assert len(sanitized["media_tags"]) == 2
    with pytest.raises(ValueError):
        plugin._validate_content_response(response, action="list")


def _configure_image_cache(monkeypatch, tmp_path):
    import hermes_constants

    home = tmp_path / "hermes-home"
    image_root = home / "cache" / "images"
    image_root.mkdir(parents=True)
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    return home, image_root


def _jpeg_bytes(payload=b"test", size=(320, 240)):
    from PIL import Image

    seed = sum(payload)
    image = Image.new("RGB", size, (seed % 256, (seed + 1) % 256, (seed + 2) % 256))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85)
    return output.getvalue()


def _saved_image_bytes(*, format_name="JPEG", size=(400, 300), color="navy", animated=False):
    from PIL import Image

    first = Image.new("RGB", size, color)
    output = io.BytesIO()
    if animated:
        second = Image.new("RGB", size, "gold")
        first.save(output, format=format_name, save_all=True, append_images=[second], duration=100, loop=0)
    else:
        first.save(output, format=format_name)
    return output.getvalue()


def _cover_response(jpeg_data=None, portrait_data=None):
    jpeg_data = jpeg_data or _jpeg_bytes()
    portrait_data = portrait_data or _jpeg_bytes(b"portrait", size=(240, 320))
    return {
        "ok": True,
        "state": "ready",
        "message": "封面候选已生成。",
        "covers": [{
            "release_id": "release-1",
            "cover_id": "a" * 64,
            "cover_sha256": "b" * 64,
            "video_sha256": "c" * 64,
            "source": "video_frame",
            "time": 1.5,
            "previews": [
                {"format": "landscape", "jpeg_base64": base64.b64encode(jpeg_data).decode("ascii")},
                {"format": "portrait", "jpeg_base64": base64.b64encode(portrait_data).decode("ascii")},
            ],
        }],
    }


def test_saved_cover_sources_use_actual_ratio_and_ignore_unapproved_files(monkeypatch, tmp_path):
    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    (release_dir / "release-1_9x16.jpg").write_bytes(_saved_image_bytes(size=(400, 300)))
    (release_dir / "release-1_3x4.jpeg").write_bytes(_saved_image_bytes(size=(300, 400)))
    (release_dir / "release-1_master.jpg").write_bytes(b"not an approved source")
    (release_dir / "release-1_9x16.zip").write_bytes(b"not an image")
    (release_dir / "release-2_4x3.jpg").write_bytes(b"another release")

    read_files = []
    read_posix = plugin._read_saved_cover_file_posix
    read_windows = plugin._read_saved_cover_file_windows

    def tracked_posix(directory_fd, filename, max_bytes):
        read_files.append(filename)
        return read_posix(directory_fd, filename, max_bytes)

    def tracked_windows(path, directory_snapshot, max_bytes):
        read_files.append(Path(path).name)
        return read_windows(path, directory_snapshot, max_bytes)

    monkeypatch.setattr(plugin, "_read_saved_cover_file_posix", tracked_posix)
    monkeypatch.setattr(plugin, "_read_saved_cover_file_windows", tracked_windows)
    scope = ("qqbot", "owner", "owner", "dm")
    sources = plugin._saved_cover_sources("release-1", scope, root=root)

    assert [source["filename"] for source in sources] == ["release-1_9x16.jpg", "release-1_3x4.jpeg"]
    assert [(source["aspect"], source["expected_aspect"]) for source in sources] == [
        ("4:3", "9:16"), ("3:4", "3:4"),
    ]
    assert all(len(source["image_id"]) == 32 for source in sources)
    assert len({source["image_id"] for source in sources}) == 2
    assert all(set(source) == {
        "image_id", "filename", "release_id", "width", "height", "aspect", "expected_aspect",
    } for source in sources)
    assert len(read_files) == 16
    assert all(plugin.re.fullmatch(r"release-1_(?:9x16|16x9|4x3|3x4)\.(?:png|jpg|jpeg|webp)", name) for name in read_files)
    assert plugin._saved_cover_sources("release-1", scope, root=root) == sources


def test_saved_cover_image_id_rejects_changed_source_content(tmp_path):
    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    source_path = release_dir / "release-1_4x3.jpg"
    source_path.write_bytes(_saved_image_bytes(size=(400, 300)))
    scope = ("qqbot", "owner", "owner", "dm")
    original = plugin._saved_cover_sources("release-1", scope, root=root)[0]

    source_path.write_bytes(_saved_image_bytes(size=(400, 300), color="tomato"))
    changed = plugin._saved_cover_sources("release-1", scope, root=root)[0]
    assert changed["image_id"] != original["image_id"]
    with pytest.raises(ValueError, match="已变更"):
        plugin._read_saved_cover_image(original["image_id"], "release-1", scope, root=root)


def test_saved_cover_sources_reject_symlinked_parent_and_child(tmp_path):
    scope = ("qqbot", "owner", "owner", "dm")
    image_data = _saved_image_bytes()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source.jpg").write_bytes(image_data)

    linked_root = tmp_path / "linked-root"
    try:
        linked_root.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前系统不允许创建测试 symlink")
    with pytest.raises(ValueError):
        plugin._saved_cover_sources("release-1", scope, root=linked_root)

    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    try:
        (release_dir / "release-1_4x3.jpg").symlink_to(outside / "source.jpg")
    except (OSError, NotImplementedError):
        pytest.skip("当前系统不允许创建测试 symlink")
    with pytest.raises(ValueError, match="普通文件"):
        plugin._saved_cover_sources("release-1", scope, root=root)


def test_saved_cover_sources_reject_oversized_and_unsafe_images(tmp_path):
    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    source_path = release_dir / "release-1_4x3.jpg"

    source_path.write_bytes(b"x" * (plugin._MAX_INBOUND_IMAGE_BYTES + 1))
    with pytest.raises(ValueError, match="大小限制"):
        plugin._saved_cover_sources("release-1", ("qqbot", "owner"), root=root)

    source_path.write_bytes(_saved_image_bytes(size=(4001, 4000)))
    with pytest.raises(ValueError):
        plugin._saved_cover_sources("release-1", ("qqbot", "owner"), root=root)

    source_path.write_bytes(b"not a valid image")
    with pytest.raises(ValueError, match="解码"):
        plugin._saved_cover_sources("release-1", ("qqbot", "owner"), root=root)


def test_saved_cover_sources_reject_animated_webp(tmp_path):
    from PIL import Image

    if "WEBP" not in Image.SAVE:
        pytest.skip("当前 Pillow 未启用 WebP 编码")
    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    (release_dir / "release-1_4x3.webp").write_bytes(
        _saved_image_bytes(format_name="WEBP", size=(400, 300), animated=True),
    )
    with pytest.raises(ValueError, match="无法安全解码"):
        plugin._saved_cover_sources("release-1", ("qqbot", "owner"), root=root)


def test_saved_cover_response_is_closed_and_reports_real_metadata():
    source = {
        "image_id": "0" * 32,
        "filename": "release-1_9x16.jpg",
        "release_id": "release-1",
        "width": 400,
        "height": 300,
        "aspect": "4:3",
        "expected_aspect": "9:16",
    }
    response = {"ok": True, "state": "ready", "message": "已列出。", "saved_sources": [source]}
    assert plugin._validate_content_response(response, action="cover_saved_sources") is response

    for invalid_source in (
        {**source, "filename": "C:\\Users\\owner\\image.jpg"},
        {**source, "aspect": "9:16"},
        {**source, "unexpected": "C:\\private"},
    ):
        with pytest.raises(ValueError):
            plugin._validate_content_response({**response, "saved_sources": [invalid_source]}, action="cover_saved_sources")
    with pytest.raises(ValueError):
        plugin._validate_content_response(response, action="list")


def test_cover_sources_are_closed_and_pair_requires_paired_images(monkeypatch, tmp_path):
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
    cover = dict(_cover_response()["covers"][0], source="paired_images")
    cover.pop("time")
    response = {"ok": True, "state": "ready", "message": "已配对。", "cover": cover}
    assert plugin._validate_content_response(response, action="cover_pair")["cover"]["source"] == "paired_images"

    for invalid_source in ("qq_image", "not-a-cover-source"):
        invalid = {**response, "cover": {**cover, "source": invalid_source}}
        with pytest.raises(ValueError):
            plugin._validate_content_response(invalid, action="cover_pair")

    allowed = _cover_response()["covers"][0]
    for source in ("qq_image", "video_frame", "library_image", "saved_image", "paired_images"):
        assert plugin._decode_cover_responses([{**allowed, "source": source}])[0][0]["source"] == source
    with pytest.raises(ValueError):
        plugin._decode_cover_responses([{**allowed, "source": "arbitrary"}])


def test_saved_cover_windows_fallback_rejects_file_replacement(monkeypatch, tmp_path):
    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    path = release_dir / "release-1_4x3.jpg"
    path.write_bytes(b"original")
    replacement = release_dir / "replacement.jpg"
    replacement.write_bytes(b"changed!")
    snapshot = plugin._saved_directory_snapshot(release_dir)
    read_no_follow = plugin._read_no_follow

    def replace_after_read(image_path, max_bytes):
        data = read_no_follow(image_path, max_bytes)
        replacement.replace(path)
        return data

    monkeypatch.setattr(plugin, "_read_no_follow", replace_after_read)
    with pytest.raises(ValueError, match="身份或内容已变化"):
        plugin._read_saved_cover_file_windows(path, snapshot, plugin._MAX_INBOUND_IMAGE_BYTES)


@pytest.mark.skipif(os.name != "posix", reason="POSIX dirfd/NOFOLLOW 链检查在 Linux CI 验证")
def test_saved_cover_posix_file_reader_rejects_replaced_name_identity(monkeypatch, tmp_path):
    from types import SimpleNamespace

    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    (release_dir / "release-1_4x3.jpg").write_bytes(b"stable source")
    directory_fd = plugin._open_saved_cover_directory(release_dir)
    original_stat = plugin.os.stat
    calls = [0]

    def replaced_name_stat(path, *args, **kwargs):
        info = original_stat(path, *args, **kwargs)
        if kwargs.get("dir_fd") is not None:
            calls[0] += 1
            if calls[0] == 2:
                fields = {
                    name: getattr(info, name)
                    for name in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
                }
                fields["st_ino"] += 1
                return SimpleNamespace(**fields)
        return info

    try:
        monkeypatch.setattr(plugin.os, "stat", replaced_name_stat)
        with pytest.raises(ValueError, match="身份或内容已变化"):
            plugin._read_saved_cover_file_posix(
                directory_fd, "release-1_4x3.jpg", plugin._MAX_INBOUND_IMAGE_BYTES,
            )
    finally:
        os.close(directory_fd)


def test_fake_qq_hook_registers_only_owner_dm_images_without_exposing_paths(owner_context, monkeypatch, tmp_path):
    """使用构造的 MessageEvent，不代表真实 QQ 端到端测试。"""
    _home, image_root = _configure_image_cache(monkeypatch, tmp_path)
    image_path = image_root / "incoming.jpg"
    image_path.write_bytes(_jpeg_bytes())

    plugin._observe_publish_confirmation(event=_message(
        "这是封面图片",
        nonce="qq-image-1",
        media_urls=[str(image_path)],
        media_types=["image/jpeg"],
    ))
    sources = json.loads(asyncio.run(plugin.handle_content({"action": "cover_sources"})))
    sources = sources["cover_sources"]
    assert len(sources) == 1
    assert set(sources[0]) == {"image_id", "received_at", "ordinal"}
    assert len(sources[0]["image_id"]) == 32
    assert sources[0]["ordinal"] == 1
    assert str(image_path) not in json.dumps(sources)

    from gateway.config import Platform

    plugin._observe_publish_confirmation(event=_message(
        "external",
        nonce="external-image-1",
        platform=Platform.TELEGRAM,
        media_urls=[str(image_path)],
        media_types=["image/jpeg"],
    ))
    plugin._observe_publish_confirmation(event=_message(
        "group",
        nonce="group-image-1",
        chat_type="group",
        media_urls=[str(image_path)],
        media_types=["image/jpeg"],
    ))
    plugin._observe_publish_confirmation(event=_message(
        "internal",
        nonce="internal-image-1",
        internal=True,
        media_urls=[str(image_path)],
        media_types=["image/jpeg"],
    ))
    assert len(plugin._INBOUND_IMAGES) == 1


def test_fake_qq_hook_rejects_external_and_symlinked_paths(owner_context, monkeypatch, tmp_path):
    """使用伪造网关事件检查本地路径边界。"""
    _home, image_root = _configure_image_cache(monkeypatch, tmp_path)
    external = tmp_path / "outside.jpg"
    external.write_bytes(_jpeg_bytes())
    plugin._observe_inbound_images(_message(
        "external path",
        nonce="outside-image-1",
        media_urls=[str(external)],
        media_types=["image/jpeg"],
    ))
    assert not plugin._INBOUND_IMAGES


def test_fake_qq_hook_uses_migrated_legacy_image_cache_path(owner_context, monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    image_root = home / "image_cache"
    image_root.mkdir(parents=True)
    image_path = image_root / "incoming.jpg"
    image_path.write_bytes(_jpeg_bytes())
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    plugin._observe_inbound_images(_message(
        "迁移目录图片",
        nonce="legacy-image-1",
        media_urls=[str(image_path)],
        media_types=["image/jpeg"],
    ))

    assert len(plugin._INBOUND_IMAGES) == 1
    assert next(iter(plugin._INBOUND_IMAGES.values()))["path"] == str(image_path)
    assert not (home / "cache" / "images").exists()


def test_fake_qq_hook_rejects_symlinked_legacy_cache_root(owner_context, monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    image_path = outside / "incoming.jpg"
    image_path.write_bytes(_jpeg_bytes())
    try:
        (home / "image_cache").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前系统不允许创建测试 symlink")
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    plugin._observe_inbound_images(_message(
        "符号链接缓存目录",
        nonce="legacy-symlink-image-1",
        media_urls=[str(home / "image_cache" / image_path.name)],
        media_types=["image/jpeg"],
    ))
    assert not plugin._INBOUND_IMAGES

    target = image_root / "actual.jpg"
    target.write_bytes(_jpeg_bytes())
    link = image_root / "linked.jpg"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("当前系统不允许创建测试 symlink")
    plugin._observe_inbound_images(_message(
        "symlink path",
        nonce="symlink-image-1",
        media_urls=[str(link)],
        media_types=["image/jpeg"],
    ))
    assert not plugin._INBOUND_IMAGES


def test_fake_qq_hook_deduplicates_message_nonce_and_expires_sources(owner_context, monkeypatch, tmp_path):
    """使用伪造 MessageEvent 检查重放去重和来源过期，不连接真实 QQ。"""
    _home, image_root = _configure_image_cache(monkeypatch, tmp_path)
    image_path = image_root / "incoming.jpg"
    image_path.write_bytes(_jpeg_bytes())
    clock = [100.0]
    monkeypatch.setattr(plugin, "_inbound_now", lambda: clock[0])
    event = _message(
        "image",
        nonce="replay-image-1",
        media_urls=[str(image_path)],
        media_types=["image/jpeg"],
    )
    plugin._observe_inbound_images(event)
    first_id = next(iter(plugin._INBOUND_IMAGES))
    plugin._observe_inbound_images(event)
    assert list(plugin._INBOUND_IMAGES) == [first_id]
    assert len(plugin._cover_sources(("qqbot", "owner", "owner", "dm"))) == 1

    clock[0] += plugin._INBOUND_IMAGE_TTL + 1
    assert plugin._cover_sources(("qqbot", "owner", "owner", "dm")) == []


def test_cover_import_reads_only_registered_qq_image_and_sends_internal_base64(owner_context, monkeypatch, tmp_path):
    """观察到的事件为伪造数据，不进行真实 QQ 端到端测试。"""
    _home, image_root = _configure_image_cache(monkeypatch, tmp_path)
    image_data = _jpeg_bytes(b"private inbound source")
    image_path = image_root / "incoming.jpg"
    image_path.write_bytes(image_data)
    plugin._observe_inbound_images(_message(
        "image",
        nonce="import-image-1",
        media_urls=[str(image_path)],
        media_types=["image/jpeg"],
    ))
    image_id = next(iter(plugin._INBOUND_IMAGES))
    requests = []

    async def request(payload):
        requests.append(payload)
        return _success_response("ready")

    monkeypatch.setattr(plugin, "_request_content", request)
    output = json.loads(asyncio.run(plugin.handle_content({
        "action": "cover_import",
        "release_id": "release-1",
        "image_id": image_id,
    })))
    assert output["state"] == "ready"
    assert len(requests) == 1
    assert set(requests[0]) == {"action", "release_id", "image_base64"}
    assert requests[0]["action"] == "cover_import"
    assert base64.b64decode(requests[0]["image_base64"], validate=True) == image_data
    assert str(image_path) not in json.dumps(requests)


def test_cover_saved_sources_reads_fixed_directory_locally(owner_context, monkeypatch, tmp_path):
    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    (release_dir / "release-1_4x3.jpg").write_bytes(_saved_image_bytes(size=(400, 300)))
    monkeypatch.setattr(plugin, "_saved_cover_root", lambda root=None: root if root is not None else tmp_path / "starlibrary_covers")
    monkeypatch.setattr(plugin, "_request_content", lambda _payload: pytest.fail("本地素材枚举不应调用 UDS"))

    output = json.loads(asyncio.run(plugin.handle_content({
        "action": "cover_saved_sources", "release_id": "release-1",
    })))
    assert output["state"] == "ready"
    assert output["saved_sources"][0]["aspect"] == "4:3"
    assert str(root) not in json.dumps(output)
    assert "image_base64" not in json.dumps(output)


def test_cover_saved_sources_reports_undelivered_directory_locally(owner_context, monkeypatch, tmp_path):
    missing_root = tmp_path / "not-delivered"
    monkeypatch.setattr(plugin, "_saved_cover_root", lambda root=None: root if root is not None else missing_root)
    monkeypatch.setattr(plugin, "_request_content", lambda _payload: pytest.fail("本地素材枚举不应调用 UDS"))
    output = json.loads(asyncio.run(plugin.handle_content({
        "action": "cover_saved_sources", "release_id": "release-1",
    })))
    assert output["state"] == "ready"
    assert output["saved_sources"] == []
    assert "制作目录尚未交付" in output["message"]


def test_cover_import_saved_rechecks_source_and_sends_only_internal_base64(owner_context, monkeypatch, tmp_path):
    root = tmp_path / "starlibrary_covers"
    release_dir = root / "release-1"
    release_dir.mkdir(parents=True)
    image_data = _saved_image_bytes(size=(400, 300), color="navy")
    source_path = release_dir / "release-1_4x3.jpg"
    source_path.write_bytes(image_data)
    monkeypatch.setattr(plugin, "_saved_cover_root", lambda root=None: root if root is not None else tmp_path / "starlibrary_covers")
    scope = plugin._owner_qq_dm_scope()
    image_id = plugin._saved_cover_sources("release-1", scope)[0]["image_id"]
    requests = []

    async def request(payload):
        requests.append(payload)
        return _success_response("ready")

    monkeypatch.setattr(plugin, "_request_content", request)
    output = json.loads(asyncio.run(plugin.handle_content({
        "action": "cover_import_saved", "release_id": "release-1", "image_id": image_id,
    })))
    assert output["state"] == "ready"
    assert requests == [{
        "action": "cover_import_saved",
        "release_id": "release-1",
        "image_base64": base64.b64encode(image_data).decode("ascii"),
    }]
    assert str(source_path) not in json.dumps(requests)

    requests.clear()
    source_path.write_bytes(_saved_image_bytes(size=(400, 300), color="gold"))
    stale = json.loads(asyncio.run(plugin.handle_content({
        "action": "cover_import_saved", "release_id": "release-1", "image_id": image_id,
    })))
    assert stale["state"] == "needs_attention"
    assert requests == []


def test_cover_pair_sends_only_validated_pair_identifiers(owner_context, monkeypatch):
    requests = []

    async def request(payload):
        requests.append(payload)
        return _success_response("ready")

    monkeypatch.setattr(plugin, "_request_content", request)
    args = {
        "action": "cover_pair",
        "release_id": "release-1",
        "landscape_cover_id": "a" * 64,
        "portrait_cover_id": "b" * 64,
        "from_release_id": "release-2",
    }
    output = json.loads(asyncio.run(plugin.handle_content(args)))
    assert output["state"] == "ready"
    assert requests == [args]


@pytest.mark.parametrize("action", ["cover_sources", "cover_import", "cover_saved_sources", "cover_import_saved", "cover_pair"])
def test_cover_sources_and_import_reject_cli_without_owner_qq_scope(owner_context, monkeypatch, action):
    def no_session_value(_name, default=""):
        return default

    monkeypatch.setattr("gateway.session_context.get_session_env", no_session_value)
    monkeypatch.setattr(plugin, "_request_content", lambda _payload: pytest.fail("不应调用 UDS"))
    args = {"action": action}
    if action in {"cover_import", "cover_import_saved"}:
        args.update(release_id="release-1", image_id="0" * 32)
    elif action == "cover_saved_sources":
        args.update(release_id="release-1")
    elif action == "cover_pair":
        args.update(release_id="release-1", landscape_cover_id="a" * 64, portrait_cover_id="b" * 64)
    result = json.loads(asyncio.run(plugin.handle_content(args)))
    assert result["state"] == "unavailable"


def test_cover_preview_base64_is_validated_removed_and_cached_safely(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    jpeg_data = _jpeg_bytes(b"deduplicated preview")
    portrait_data = _jpeg_bytes(b"portrait preview", size=(240, 320))
    response = _cover_response(jpeg_data, portrait_data)
    sanitized = plugin._validate_content_response(response, action="covers")
    second = plugin._validate_content_response(response, action="covers")

    assert "jpeg_base64" not in json.dumps(sanitized)
    assert len(sanitized["media_tags"]) == 2
    assert all(item["cover_id"] == "a" * 64 for item in sanitized["media_tags"])
    paths = [Path(item["media_tag"].removeprefix("MEDIA:")) for item in sanitized["media_tags"]]
    repeated_paths = [Path(item["media_tag"].removeprefix("MEDIA:")) for item in second["media_tags"]]
    assert paths == repeated_paths
    assert paths[0].read_bytes() == jpeg_data
    assert paths[1].read_bytes() == portrait_data
    if os.name == "posix":
        for path in paths:
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_cover_preview_pruning_limits_scope_and_preserves_current_batch(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    cache = plugin._cover_cache_directory()
    now = plugin.time.time()
    for index in range(205):
        name = plugin.hashlib.sha256(f"seed-{index}".encode()).hexdigest() + ".jpg"
        path = cache / name
        path.write_bytes(b"old preview")
        os.utime(path, (now - 3600, now - 3600))

    stale = cache / (plugin.hashlib.sha256(b"stale").hexdigest() + ".jpg")
    stale.write_bytes(b"expired preview")
    os.utime(stale, (now - plugin._COVER_CACHE_TTL_SECONDS - 1,) * 2)
    nonmatching = cache / "notes.jpg"
    nonmatching.write_bytes(b"keep")
    directory = cache / (("d" * 64) + ".jpg")
    directory.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    link = cache / (("e" * 64) + ".jpg")
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        link = None

    other_cache = home / "cache" / "images"
    other_cache.mkdir()
    other_file = other_cache / "keep.jpg"
    other_file.write_bytes(b"unrelated")

    base_cover = _cover_response()["covers"][0]
    covers = []
    for index in range(5):
        cover = dict(base_cover)
        cover["release_id"] = f"release-{index + 1}"
        cover["cover_id"] = f"{index + 1:064x}"
        cover["cover_sha256"] = f"{index + 101:064x}"
        cover["video_sha256"] = f"{index + 201:064x}"
        cover["previews"] = []
        for offset, (format_name, size) in enumerate((("landscape", (320, 240)), ("portrait", (240, 320)))):
            image_data = _jpeg_bytes(bytes([index * 2 + offset + 1]), size=size)
            cover["previews"].append({
                "format": format_name,
                "jpeg_base64": base64.b64encode(image_data).decode("ascii"),
            })
        covers.append(cover)

    response = _cover_response()
    response["covers"] = covers
    sanitized = plugin._validate_content_response(response, action="covers")
    current_paths = [
        Path(item["media_tag"].removeprefix("MEDIA:"))
        for item in sanitized["media_tags"]
    ]

    assert len(current_paths) == 10
    assert all(path.is_file() for path in current_paths)
    assert not stale.exists()
    matching_files = [
        path for path in cache.iterdir()
        if plugin._COVER_CACHE_FILENAME_RE.fullmatch(path.name)
        and stat.S_ISREG(path.lstat().st_mode)
    ]
    assert len(matching_files) == plugin._MAX_COVER_CACHE_FILES
    assert all(path.exists() for path in current_paths)
    assert nonmatching.read_bytes() == b"keep"
    assert directory.is_dir()
    assert outside.read_bytes() == b"outside"
    if link is not None:
        assert link.is_symlink()
    assert other_file.read_bytes() == b"unrelated"


def test_cover_import_response_preview_is_sanitized_only_for_cover_import(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    response = _cover_response()
    imported_cover = dict(response["covers"][0], source="qq_image")
    imported_cover.pop("time")
    import_response = {key: value for key, value in response.items() if key != "covers"}
    import_response["cover"] = imported_cover

    sanitized = plugin._validate_content_response(import_response, action="cover_import")
    assert sanitized["cover"]["source"] == "qq_image"
    assert "time" not in sanitized["cover"]
    assert "jpeg_base64" not in json.dumps(sanitized)
    assert len(sanitized["media_tags"]) == 2
    assert all(item["cover_id"] == imported_cover["cover_id"] for item in sanitized["media_tags"])

    with pytest.raises(ValueError):
        plugin._validate_content_response(import_response, action="list")
    with pytest.raises(ValueError):
        plugin._validate_content_response(response, action="cover_import")


@pytest.mark.parametrize(("action", "source_name"), [
    ("cover_import_saved", "saved_image"),
    ("cover_pair", "paired_images"),
])
def test_saved_image_and_pair_responses_use_standard_safe_preview_pipeline(monkeypatch, tmp_path, action, source_name):
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
    cover = dict(_cover_response()["covers"][0], source=source_name)
    cover.pop("time")
    response = {"ok": True, "state": "ready", "message": "已生成。", "cover": cover}

    sanitized = plugin._validate_content_response(response, action=action)
    assert sanitized["cover"]["source"] == source_name
    assert "jpeg_base64" not in json.dumps(sanitized)
    assert len(sanitized["media_tags"]) == 2
    with pytest.raises(ValueError):
        plugin._validate_content_response(response, action="list")


@pytest.mark.parametrize("jpeg_data,action", [
    (b"not-a-jpeg" + b"x" * 32, "covers"),
    (b"\xff\xd8\xff" + b"x" * (plugin._MAX_COVER_PREVIEW_BYTES + 1) + b"\xff\xd9", "covers"),
], ids=["not-jpeg", "oversized"])
def test_cover_preview_rejects_invalid_or_oversized_jpeg(monkeypatch, tmp_path, jpeg_data, action):
    home = tmp_path / "hermes-home"
    home.mkdir()
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    with pytest.raises(ValueError):
        plugin._validate_content_response(_cover_response(jpeg_data), action=action)


def test_cover_preview_rejects_jpeg_markers_without_decodable_image(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    invalid_jpeg = b"\xff\xd8\xffnot-a-decodable-jpeg\xff\xd9"
    with pytest.raises(ValueError):
        plugin._validate_content_response(_cover_response(invalid_jpeg), action="covers")


@pytest.mark.parametrize(
    "size,is_animated,n_frames",
    [((4001, 4000), False, 1), ((321, 240), False, 1), ((320, 240), True, 2)],
    ids=["pixel-limit", "fixed-size", "animated"],
)
def test_cover_preview_rejects_unsafe_dimensions_and_animation(monkeypatch, size, is_animated, n_frames):
    from PIL import Image

    class FakeImage:
        format = "JPEG"

        def __init__(self):
            self.size = size
            self.is_animated = is_animated
            self.n_frames = n_frames

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def load(self):
            pytest.fail("无效尺寸或动画图片不应解码")

    monkeypatch.setattr(Image, "open", lambda *_args, **_kwargs: FakeImage())
    with pytest.raises(ValueError):
        plugin._validate_cover_preview_jpeg(b"not-used-by-mock", "landscape")


def test_cover_response_rejects_base64_outside_cover_preview_and_paths(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    malicious = {"ok": True, "state": "ready", "message": "ok", "plan": {"preview": base64.b64encode(_jpeg_bytes(b"x" * 24)).decode()}}
    with pytest.raises(ValueError):
        plugin._validate_content_response(malicious, action="list")

    path_source = _cover_response()
    path_source["covers"][0]["source"] = "C:\\private\\secret.jpg"
    with pytest.raises(ValueError):
        plugin._validate_content_response(path_source, action="covers")
    assert not (home / "cache" / "douyin-covers").exists()


def test_cover_response_rejects_symlinked_output_directory(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "cache").mkdir()
    try:
        (home / "cache" / "douyin-covers").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前系统不允许创建测试 symlink")
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: home)
    with pytest.raises(ValueError):
        plugin._validate_content_response(_cover_response(), action="covers")
    assert not list(outside.iterdir())
