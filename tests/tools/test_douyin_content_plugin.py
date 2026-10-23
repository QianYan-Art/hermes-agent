"""抖音内容工具的RPC协议和发布确认门禁。"""

import asyncio
import base64
import importlib.util
import io
import json
import os
import stat
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

    assert set(ctx.tools) == {"douyin_login", "douyin_content"}
    assert ctx.tools["douyin_login"]["toolset"] == "douyin"
    assert ctx.tools["douyin_login"]["schema"]["parameters"]["properties"]["action"]["enum"] == ["status", "login"]
    assert ctx.tools["douyin_content"]["toolset"] == "douyin"
    assert ctx.tools["douyin_content"]["schema"]["parameters"]["additionalProperties"] is False
    assert "confirmed" not in ctx.tools["douyin_content"]["schema"]["parameters"]["properties"]
    content_schema = ctx.tools["douyin_content"]["schema"]
    assert content_schema["parameters"]["properties"]["action"]["enum"] == [
        "list", "metrics", "covers", "cover_sources", "cover_import", "prepare", "stage", "draft", "job", "publish"
    ]
    assert "15 分钟" in content_schema["description"]
    assert "job 查询不会导航" in content_schema["description"]
    assert "另一次 prepare" in content_schema["description"]
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


@pytest.mark.parametrize("action", ["cover_sources", "cover_import"])
def test_cover_sources_and_import_reject_cli_without_owner_qq_scope(owner_context, monkeypatch, action):
    def no_session_value(_name, default=""):
        return default

    monkeypatch.setattr("gateway.session_context.get_session_env", no_session_value)
    monkeypatch.setattr(plugin, "_request_content", lambda _payload: pytest.fail("不应调用 UDS"))
    args = {"action": action}
    if action == "cover_import":
        args.update(release_id="release-1", image_id="0" * 32)
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
