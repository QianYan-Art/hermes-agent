"""通过本机受限套接字访问独立抖音登录服务。"""

import asyncio
import base64
import binascii
import json
import os
from pathlib import Path
import stat
import tempfile
import time

SOCKET_PATH = "/run/hermes-douyin/login.sock"
MAX_RESPONSE = 3 * 1024 * 1024
MAX_PNG = 2 * 1024 * 1024
STATES = {
    "logged_in", "login_required", "verification_required", "account_mismatch",
    "unknown", "page_error", "unavailable",
}


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
