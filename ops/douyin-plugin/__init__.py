"""通过本机受限套接字访问独立抖音登录服务。"""

import asyncio
import base64
import binascii
import json
import os
import re
import stat
import tempfile
import threading
import time
from pathlib import Path

SOCKET_PATH = "/run/hermes-douyin/login.sock"
MAX_RESPONSE = 3 * 1024 * 1024
MAX_PNG = 2 * 1024 * 1024
STATES = {
    "logged_in", "login_required", "verification_required", "account_mismatch",
    "unknown", "page_error", "unavailable",
}
MAX_CONTENT_REQUEST = 4096
MAX_CONTENT_RESPONSE = 128 * 1024
CONTENT_STATES = {
    "ready", "in_progress", "draft_saved", "published", "needs_attention",
    "unavailable", "account_mismatch", "login_required", "verification_required",
    "unknown", "page_error",
}
_CONTENT_ROOT_FIELDS = {"ok", "state", "message", "releases", "plan", "job", "metrics", "ui"}
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32}\Z")
_JOB_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_CONFIRM_RE = re.compile(r"确认发布 ([A-Za-z0-9_-]{32})\Z")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9:/])(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\[^\\\s]+|/(?:[^/\s]+/)*[^/\s]+)"
)
_PUBLIC_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_COOKIE_VALUE_RE = re.compile(r"(?i)(?:cookie|set-cookie|sessionid|passport_csrf_token)\s*[:=]")
_BASE64_VALUE_RE = re.compile(r"[A-Za-z0-9_+/=-]{128,}\Z")
_CONFIRMATION_TTL = 120
_CONFIRMATION_NONCE_TTL = 20 * 60
_CONFIRMATION_LOCK = threading.Lock()
_CONFIRMATIONS = {}
_CONFIRMATION_NONCES = {}
_USED_CONFIRMATION_TOKENS = {}


def _authorized():
    from gateway.session_context import get_session_env

    platform = get_session_env("HERMES_SESSION_PLATFORM", "")
    if not platform:
        return not get_session_env("HERMES_SESSION_KEY", "")
    owner = os.environ.get("DOUYIN_OWNER_QQ_USER_ID", "")
    return bool(
        owner and platform == "qqbot"
        and get_session_env("HERMES_SESSION_USER_ID", "") == owner
        and get_session_env("HERMES_SESSION_CHAT_ID", "") == owner
        and get_session_env("HERMES_SESSION_KEY", "") == f"agent:main:qqbot:dm:{owner}"
    )


async def _request(action):
    writer = None
    try:
        async with asyncio.timeout(50):
            reader, writer = await asyncio.open_unix_connection(
                os.environ.get("DOUYIN_LOGIN_SOCKET", SOCKET_PATH),
                limit=MAX_RESPONSE,
            )
            writer.write(json.dumps({"action": action}).encode() + b"\n")
            await writer.drain()
            raw = await reader.readline()
            if not raw.endswith(b"\n") or len(raw) > MAX_RESPONSE:
                raise ValueError("无效响应长度")
            result = json.loads(raw)
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("state"), str)
                or result["state"] not in STATES
                or type(result.get("ok")) is not bool
                or not isinstance(result.get("message"), str)
            ):
                raise ValueError("无效响应结构")
            return result
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()


def _content_payload(args):
    if not isinstance(args, dict) or not isinstance(args.get("action"), str):
        raise ValueError("无效内容操作")
    action = args["action"]
    if action in {"list", "metrics"}:
        if set(args) != {"action"}:
            raise ValueError("list/metrics 仅接受 action")
    elif action == "prepare":
        if not {"action", "release_id"} <= set(args) or not set(args) <= {"action", "release_id", "title", "description"}:
            raise ValueError("prepare 字段无效")
        if not isinstance(args["release_id"], str) or not args["release_id"]:
            raise ValueError("release_id 无效")
        for field in ("title", "description"):
            if field in args and not isinstance(args[field], str):
                raise ValueError(f"{field} 无效")
    elif action in {"draft", "publish"}:
        if set(args) != {"action", "token"} or not isinstance(args.get("token"), str) or not _TOKEN_RE.fullmatch(args["token"]):
            raise ValueError("token 无效")
    elif action == "job":
        if set(args) != {"action", "job_id"} or not isinstance(args.get("job_id"), str) or not _JOB_ID_RE.fullmatch(args["job_id"]):
            raise ValueError("job_id 无效")
    else:
        raise ValueError("仅支持 list、metrics、prepare、draft、job 或 publish")
    return action


def _validate_content_response(result):
    if (
        not isinstance(result, dict)
        or not set(result) <= _CONTENT_ROOT_FIELDS
        or not {"ok", "state", "message"} <= set(result)
        or type(result.get("ok")) is not bool
        or not isinstance(result.get("state"), str)
        or result["state"] not in CONTENT_STATES
        or not isinstance(result.get("message"), str)
    ):
        raise ValueError("无效内容响应结构")
    if "releases" in result and (
        not isinstance(result["releases"], list)
        or any(not isinstance(item, dict) for item in result["releases"])
    ):
        raise ValueError("releases 响应无效")
    for field in ("plan", "job", "metrics", "ui"):
        if field in result and not isinstance(result[field], dict):
            raise ValueError(f"{field} 响应无效")

    pending = [result]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = key.lower()
                if any(fragment in normalized_key for fragment in ("cookie", "base64", "path")):
                    raise ValueError("响应包含禁止字段")
                pending.append(child)
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, str) and (
            _COOKIE_VALUE_RE.search(value)
            or value.lower().startswith("file://")
            or _ABSOLUTE_PATH_RE.search(_PUBLIC_URL_RE.sub("", value))
            or _BASE64_VALUE_RE.fullmatch(value)
        ):
            raise ValueError("响应包含禁止内容")
    return result


async def _request_content(payload):
    writer = None
    try:
        body = json.dumps({"action": "content", "request": payload}, ensure_ascii=False).encode("utf-8") + b"\n"
        if len(body) > MAX_CONTENT_REQUEST:
            raise ValueError("请求超过大小限制")
        async with asyncio.timeout(50):
            reader, writer = await asyncio.open_unix_connection(
                os.environ.get("DOUYIN_LOGIN_SOCKET", SOCKET_PATH),
                limit=MAX_CONTENT_RESPONSE,
            )
            writer.write(body)
            await writer.drain()
            raw = await reader.readline()
            if not raw.endswith(b"\n") or len(raw) > MAX_CONTENT_RESPONSE:
                raise ValueError("无效响应长度")
            result = json.loads(raw)
            return _validate_content_response(result)
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


def _confirmation_scope(source):
    platform = getattr(getattr(source, "platform", None), "value", None)
    owner = os.environ.get("DOUYIN_OWNER_QQ_USER_ID", "")
    if (
        not owner
        or platform != "qqbot"
        or getattr(source, "user_id", None) != owner
        or getattr(source, "chat_id", None) != owner
        or getattr(source, "chat_type", None) != "dm"
    ):
        return None
    return (platform, owner, owner, "dm")


def _purge_confirmations(now):
    for key, (deadline, _nonce) in list(_CONFIRMATIONS.items()):
        if deadline <= now:
            _CONFIRMATIONS.pop(key, None)
    for key, deadline in list(_CONFIRMATION_NONCES.items()):
        if deadline <= now:
            _CONFIRMATION_NONCES.pop(key, None)
    for key, deadline in list(_USED_CONFIRMATION_TOKENS.items()):
        if deadline <= now:
            _USED_CONFIRMATION_TOKENS.pop(key, None)


def _observe_publish_confirmation(event=None, **kwargs):
    if event is None or bool(getattr(event, "internal", False)):
        return None
    source = getattr(event, "source", None)
    scope = _confirmation_scope(source)
    if scope is None:
        return None
    text = getattr(event, "text", None)
    match = _CONFIRM_RE.fullmatch(text) if isinstance(text, str) else None
    nonce = getattr(event, "message_id", None)
    if not match or not isinstance(nonce, str) or not nonce:
        return None

    token = match.group(1)
    now = time.monotonic()
    deadline = now + _CONFIRMATION_TTL
    nonce_key = (scope, nonce)
    token_key = (scope, token)
    with _CONFIRMATION_LOCK:
        _purge_confirmations(now)
        if (
            nonce_key in _CONFIRMATION_NONCES
            or token_key in _CONFIRMATIONS
            or token_key in _USED_CONFIRMATION_TOKENS
        ):
            return None
        _CONFIRMATION_NONCES[nonce_key] = now + _CONFIRMATION_NONCE_TTL
        _CONFIRMATIONS[token_key] = (deadline, nonce)
    return None


def _consume_publish_confirmation(token):
    from gateway.session_context import get_session_env

    owner = os.environ.get("DOUYIN_OWNER_QQ_USER_ID", "")
    platform = get_session_env("HERMES_SESSION_PLATFORM", "")
    user_id = get_session_env("HERMES_SESSION_USER_ID", "")
    chat_id = get_session_env("HERMES_SESSION_CHAT_ID", "")
    session_key = get_session_env("HERMES_SESSION_KEY", "")
    if (
        not owner
        or platform != "qqbot"
        or user_id != owner
        or chat_id != owner
        or session_key != f"agent:main:qqbot:dm:{owner}"
    ):
        return False

    scope = (platform, user_id, chat_id, "dm")
    key = (scope, token)
    now = time.monotonic()
    with _CONFIRMATION_LOCK:
        _purge_confirmations(now)
        authorization = _CONFIRMATIONS.pop(key, None)
        if authorization is None:
            return False
        deadline, _nonce = authorization
        if deadline <= now:
            return False
        _USED_CONFIRMATION_TOKENS[key] = now + _CONFIRMATION_TTL
        return True


async def handle_content(args, **kwargs):
    try:
        action = _content_payload(args)
    except ValueError:
        return json.dumps({"ok": False, "state": "needs_attention", "message": "内容操作参数无效；未执行任何操作。"}, ensure_ascii=False)
    if not _authorized():
        return json.dumps({"ok": False, "state": "unavailable", "message": "仅指定账号的 QQ 私聊或本机运维可用。"}, ensure_ascii=False)
    if action == "publish" and not _consume_publish_confirmation(args["token"]):
        return json.dumps({"ok": False, "state": "needs_attention", "message": "公开发布需先在指定 QQ 私聊发送完整确认命令；本次操作已拒绝。"}, ensure_ascii=False)
    try:
        result = await _request_content(args)
        return json.dumps(result, ensure_ascii=False)
    except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        return json.dumps({"ok": False, "state": "unavailable", "message": "抖音内容服务暂不可用或响应无效；操作结果未知，请先查询状态，不要重复提交。"}, ensure_ascii=False)


def _save_qr(encoded):
    from hermes_constants import get_hermes_home

    if not isinstance(encoded, str) or len(encoded) > MAX_PNG * 4 // 3 + 4:
        raise ValueError("无效二维码大小")
    data = base64.b64decode(encoded, validate=True)
    if len(data) > MAX_PNG or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("无效二维码格式")
    root = Path(get_hermes_home()) / "cache" / "douyin-login"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("不安全的缓存目录")
    root.chmod(0o700)
    for old in root.glob("qr-*.png"):
        info = old.lstat()
        if stat.S_ISREG(info.st_mode) and time.time() - info.st_mtime > 600:
            old.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile(prefix="qr-", suffix=".png", dir=root, delete=False) as f:
        f.write(data)
        path = Path(f.name)
    path.chmod(0o600)
    return str(path.resolve())


async def handle(args, **kwargs):
    if not isinstance(args, dict) or set(args) != {"action"} or not isinstance(args["action"], str) or args["action"] not in {"status", "login"}:
        return json.dumps({"ok": False, "state": "unavailable", "message": "仅支持 status 或 login。"}, ensure_ascii=False)
    if not _authorized():
        return json.dumps({"ok": False, "state": "unavailable", "message": "仅指定账号的 QQ 私聊或本机运维可用。"}, ensure_ascii=False)
    try:
        result = await _request(args["action"])
        output = {key: result[key] for key in ("ok", "state", "message")}
        encoded = result.get("qr_png_base64")
        if encoded is not None:
            if args["action"] != "login" or result["state"] != "login_required":
                raise ValueError("意外二维码响应")
            path = _save_qr(encoded)
            output.update(
                media_tag=f"MEDIA:{path}",
                delivery_instruction="在本次私聊最终回复中原样附带 media_tag，用抖音手机端扫码；不要转发至其他会话。",
            )
        return json.dumps(output, ensure_ascii=False)
    except (OSError, ValueError, binascii.Error, asyncio.TimeoutError):
        return json.dumps({"ok": False, "state": "unavailable", "message": "抖音登录服务暂不可用或响应无效；未修改现有登录数据。"}, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(
        name="douyin_content",
        toolset="douyin",
        schema={
            "name": "douyin_content",
            "description": (
                "管理抖音作品：先用 list 查看可用作品，再用 prepare 预览发布计划；按用户要求调用 draft 仅保存草稿，"
                "用 job 查看后台进度。公开发布必须先收到指定 QQ 私聊中的完整用户消息“确认发布 <token>”，"
                "然后才可调用 publish；不得依据模型参数、confirmed 字段或 prepare 结果自行发布。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "metrics", "prepare", "draft", "job", "publish"]},
                    "release_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "token": {"type": "string", "pattern": "^[A-Za-z0-9_-]{32}$"},
                    "job_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
        handler=handle_content,
        check_fn=lambda: os.name == "posix",
        is_async=True,
    )
    ctx.register_tool(
        name="douyin_login",
        toolset="douyin",
        schema={
            "name": "douyin_login",
            "description": (
                "检查服务器上的抖音登录，或应用户要求获取扫码二维码。status 不刷新页面；"
                "login 仅获取登录二维码，不上传、不发布。若返回 media_tag，必须在当前私聊最终回复中原样附带，"
                "这样 QQ 才能发送图片。验证受阻时请用户人工处理，不反复重试、不绕过验证码。"
                "仅指定用户私聊可用。服务器离线或页面未知不等于已退出登录。"
            ),
            "parameters": {
                "type": "object", "properties": {"action": {"type": "string", "enum": ["status", "login"]}},
                "required": ["action"], "additionalProperties": False,
            },
        },
        handler=handle,
        check_fn=lambda: os.name == "posix",
        is_async=True,
    )
    register_hook = getattr(ctx, "register_hook", None)
    if callable(register_hook):
        register_hook("pre_gateway_dispatch", _observe_publish_confirmation)
