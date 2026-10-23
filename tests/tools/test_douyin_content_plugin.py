"""抖音内容工具的RPC协议和发布确认门禁。"""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("douyin_content_plugin_test", ROOT / "ops/douyin-plugin/__init__.py")
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)

TOKEN = "a" * 32
OTHER_TOKEN = "b" * 32


@pytest.fixture(autouse=True)
def clear_confirmation_state():
    with plugin._CONFIRMATION_LOCK:
        plugin._CONFIRMATIONS.clear()
        plugin._CONFIRMATION_NONCES.clear()
        plugin._USED_CONFIRMATION_TOKENS.clear()
    yield
    with plugin._CONFIRMATION_LOCK:
        plugin._CONFIRMATIONS.clear()
        plugin._CONFIRMATION_NONCES.clear()
        plugin._USED_CONFIRMATION_TOKENS.clear()


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
    )
    try:
        yield owner
    finally:
        clear_session_vars(tokens)


def _message(text, *, platform=None, user_id="owner", chat_id="owner", chat_type="dm", internal=False, nonce="msg-1"):
    from gateway.config import Platform
    from gateway.platforms.base import MessageEvent
    from gateway.session import SessionSource

    source = SessionSource(
        platform=platform or Platform.QQBOT,
        chat_id=chat_id,
        chat_type=chat_type,
        user_id=user_id,
    )
    return MessageEvent(text=text, source=source, message_id=nonce, internal=internal)


def _success_response(state="published"):
    return {"ok": True, "state": state, "message": "已完成。"}


@pytest.mark.parametrize("args", [
    {"action": "list", "confirmed": True},
    {"action": "metrics", "release_id": "release-1"},
    {"action": "prepare", "release_id": "release-1", "url": "https://example.org"},
    {"action": "draft", "token": TOKEN, "confirmed": True},
    {"action": "job", "job_id": "0" * 32, "path": "C:\\secret"},
    {"action": "publish", "token": TOKEN, "confirmed": True},
])
def test_content_payload_rejects_fields_outside_action_protocol(args):
    with pytest.raises(ValueError):
        plugin._content_payload(args)


def test_content_payload_accepts_only_documented_action_shapes():
    assert plugin._content_payload({"action": "list"}) == "list"
    assert plugin._content_payload({"action": "metrics"}) == "metrics"
    assert plugin._content_payload({"action": "prepare", "release_id": "release-1", "title": "标题"}) == "prepare"
    assert plugin._content_payload({"action": "draft", "token": TOKEN}) == "draft"
    assert plugin._content_payload({"action": "job", "job_id": "0" * 32}) == "job"
    assert plugin._content_payload({"action": "publish", "token": TOKEN}) == "publish"


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
    assert seen["limit"] == 128 * 1024
    assert json.loads(seen["body"]) == {"action": "content", "request": {"action": "list"}}
    assert seen["body"].endswith(b"\n")


def test_content_rpc_enforces_request_and_response_byte_limits(monkeypatch):
    async def unexpected_connection(*args, **kwargs):
        raise AssertionError("请求超限时不应连接服务")

    monkeypatch.setattr(plugin.asyncio, "open_unix_connection", unexpected_connection, raising=False)
    with pytest.raises(ValueError):
        asyncio.run(plugin._request_content({"action": "prepare", "release_id": "r", "description": "x" * 5000}))

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

    assert set(ctx.tools) == {"douyin_login", "douyin_content"}
    assert ctx.tools["douyin_login"]["toolset"] == "douyin"
    assert ctx.tools["douyin_login"]["schema"]["parameters"]["properties"]["action"]["enum"] == ["status", "login"]
    assert ctx.tools["douyin_content"]["toolset"] == "douyin"
    assert ctx.tools["douyin_content"]["schema"]["parameters"]["additionalProperties"] is False
    assert "confirmed" not in ctx.tools["douyin_content"]["schema"]["parameters"]["properties"]
    assert ctx.hooks == [("pre_gateway_dispatch", plugin._observe_publish_confirmation)]


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
