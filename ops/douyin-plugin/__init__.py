"""通过本机受限套接字访问独立抖音登录服务。"""

import asyncio
import base64
import binascii
import hashlib
import io
import json
import math
import os
import re
import secrets
import stat
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SOCKET_PATH = "/run/hermes-douyin/login.sock"
MAX_RESPONSE = 3 * 1024 * 1024
MAX_PNG = 2 * 1024 * 1024
STATES = {
    "logged_in", "login_required", "verification_required", "account_mismatch",
    "unknown", "page_error", "unavailable",
}
MAX_CONTENT_REQUEST = 12 * 1024 * 1024
MAX_CONTENT_RESPONSE = 1 * 1024 * 1024
CONTENT_STATES = {
    "ready", "in_progress", "draft_saved", "published", "needs_attention",
    "editor_ready", "unavailable", "account_mismatch", "login_required", "verification_required",
    "unknown", "page_error",
}
_CONTENT_ROOT_FIELDS = {
    "ok", "state", "message", "releases", "plan", "job", "metrics", "ui",
    "covers", "cover_sources", "cover",
}
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{32}\Z")
_JOB_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_IMAGE_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
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
_INBOUND_IMAGE_TTL = 30 * 60
_MAX_INBOUND_IMAGES = 20
_MAX_INBOUND_NONCES = 2048
_MAX_INBOUND_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_COVER_PREVIEW_BYTES = 32 * 1024
_MAX_COVER_PREVIEW_PIXELS = 16_000_000
_COVER_PREVIEW_SIZES = {"landscape": (320, 240), "portrait": (240, 320)}
_MAX_COVER_CACHE_FILES = 200
_COVER_CACHE_TTL_SECONDS = 24 * 60 * 60
_COVER_CACHE_FILENAME_RE = re.compile(r"[0-9a-f]{64}\.jpg\Z")
_INBOUND_IMAGE_LOCK = threading.Lock()
_INBOUND_IMAGES = {}
_INBOUND_IMAGE_NONCES = {}
_COVER_CACHE_LOCK = threading.RLock()


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


def _owner_qq_dm_scope():
    from gateway.session_context import get_session_env

    owner = os.environ.get("DOUYIN_OWNER_QQ_USER_ID", "")
    if (
        owner
        and get_session_env("HERMES_SESSION_PLATFORM", "") == "qqbot"
        and get_session_env("HERMES_SESSION_USER_ID", "") == owner
        and get_session_env("HERMES_SESSION_CHAT_ID", "") == owner
        and get_session_env("HERMES_SESSION_KEY", "") == f"agent:main:qqbot:dm:{owner}"
    ):
        return ("qqbot", owner, owner, "dm")
    return None


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


def _valid_release_id(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value == value.strip()
        and not any(ord(char) < 32 for char in value)
    )


def _valid_publish_at(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _content_payload(args):
    if not isinstance(args, dict) or not isinstance(args.get("action"), str):
        raise ValueError("无效内容操作")
    action = args["action"]
    if action in {"list", "metrics"}:
        if set(args) != {"action"}:
            raise ValueError("list/metrics 仅接受 action")
    elif action == "covers":
        if not {"action", "release_id"} <= set(args) or not set(args) <= {"action", "release_id", "times"}:
            raise ValueError("covers 字段无效")
        if not _valid_release_id(args["release_id"]):
            raise ValueError("release_id 无效")
        if "times" in args and (
            not isinstance(args["times"], list)
            or len(args["times"]) > 5
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
                for value in args["times"]
            )
        ):
            raise ValueError("times 必须是最多五个非负有限秒数")
    elif action == "cover_sources":
        if set(args) != {"action"}:
            raise ValueError("cover_sources 仅接受 action")
    elif action == "cover_import":
        if set(args) != {"action", "release_id", "image_id"}:
            raise ValueError("cover_import 字段无效")
        if not _valid_release_id(args.get("release_id")):
            raise ValueError("release_id 无效")
        if not isinstance(args.get("image_id"), str) or not _IMAGE_ID_RE.fullmatch(args["image_id"]):
            raise ValueError("image_id 无效")
    elif action == "prepare":
        allowed = {"action", "release_id", "title", "description", "cover_id", "visibility", "publish_at"}
        if not {"action", "release_id", "cover_id"} <= set(args) or not set(args) <= allowed:
            raise ValueError("prepare 字段无效")
        if not _valid_release_id(args["release_id"]):
            raise ValueError("release_id 无效")
        for field in ("title", "description"):
            if field in args and not isinstance(args[field], str):
                raise ValueError(f"{field} 无效")
        if not isinstance(args["cover_id"], str) or not _SHA256_RE.fullmatch(args["cover_id"]):
            raise ValueError("cover_id 无效")
        if "visibility" in args and (
            not isinstance(args["visibility"], str)
            or args["visibility"] not in {"public", "friends", "private"}
        ):
            raise ValueError("visibility 无效")
        if "publish_at" in args and not _valid_publish_at(args["publish_at"]):
            raise ValueError("publish_at 必须包含时区")
    elif action == "stage":
        if set(args) != {"action", "token"} or not isinstance(args.get("token"), str) or not _TOKEN_RE.fullmatch(args["token"]):
            raise ValueError("token 无效")
    elif action in {"draft", "publish"}:
        if set(args) != {"action", "token"} or not isinstance(args.get("token"), str) or not _TOKEN_RE.fullmatch(args["token"]):
            raise ValueError("token 无效")
    elif action == "job":
        if set(args) != {"action", "job_id"} or not isinstance(args.get("job_id"), str) or not _JOB_ID_RE.fullmatch(args["job_id"]):
            raise ValueError("job_id 无效")
    else:
        raise ValueError("内容操作 action 无效")
    return action


def _hermes_home():
    from hermes_constants import get_hermes_home

    return Path(get_hermes_home()).absolute()


def _checked_directory(path, *, create=False, private=False):
    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if create:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("不安全的缓存目录")
    if private and os.name == "posix":
        absolute.chmod(0o700)
    return absolute


def _inbound_image_path(value):
    if not isinstance(value, str):
        return None
    try:
        from hermes_constants import get_hermes_dir

        root = Path(get_hermes_dir("cache/images", "image_cache"))
        candidate = Path(value)
        if not candidate.is_absolute() or ".." in candidate.parts:
            return None
        candidate = candidate.absolute()
        relative = candidate.relative_to(root)
        if not relative.parts or candidate.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            return None
        _checked_directory(root)
        current = root
        for part in relative.parts[:-1]:
            current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                return None
        info = candidate.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_size > _MAX_INBOUND_IMAGE_BYTES
        ):
            return None
        return candidate
    except (OSError, ValueError, TypeError):
        return None


def _read_no_follow(path, max_bytes):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError("图片文件无效")
        with os.fdopen(fd, "rb", closefd=False) as image_file:
            data = image_file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("图片超过大小限制")
        return data
    finally:
        os.close(fd)


def _cover_cache_directory():
    return _checked_directory(_hermes_home() / "cache" / "douyin-covers", create=True, private=True)


def _prune_cover_cache(protected_names=()):
    protected = {
        name for name in protected_names
        if isinstance(name, str) and _COVER_CACHE_FILENAME_RE.fullmatch(name)
    }
    with _COVER_CACHE_LOCK:
        cache_dir = _cover_cache_directory()
        now = time.time()
        entries = []
        for path in cache_dir.iterdir():
            if not _COVER_CACHE_FILENAME_RE.fullmatch(path.name):
                continue
            try:
                info = path.lstat()
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                continue
            entries.append((path, info.st_mtime))

        retained = []
        for path, mtime in entries:
            try:
                current = path.lstat()
            except OSError:
                continue
            if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
                continue
            if now - mtime > _COVER_CACHE_TTL_SECONDS and path.name not in protected:
                try:
                    path.unlink()
                    continue
                except OSError:
                    pass
            retained.append((path, mtime))

        overflow = len(retained) - _MAX_COVER_CACHE_FILES
        for path, _mtime in sorted(retained, key=lambda item: item[1]):
            if overflow <= 0:
                break
            if path.name in protected:
                continue
            try:
                current = path.lstat()
                if stat.S_ISREG(current.st_mode) and not stat.S_ISLNK(current.st_mode):
                    path.unlink()
                    overflow -= 1
            except OSError:
                continue


def _save_cover_preview(data):
    if (
        not isinstance(data, bytes)
        or len(data) > _MAX_COVER_PREVIEW_BYTES
        or not data.startswith(b"\xff\xd8\xff")
        or not data.endswith(b"\xff\xd9")
    ):
        raise ValueError("JPEG 预览无效")
    digest = hashlib.sha256(data).hexdigest()
    destination = _cover_cache_directory() / f"{digest}.jpg"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with _COVER_CACHE_LOCK:
        try:
            fd = os.open(destination, flags, 0o600)
        except FileExistsError:
            info = destination.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise ValueError("不安全的预览缓存文件")
            existing = _read_no_follow(destination, _MAX_COVER_PREVIEW_BYTES)
            if hashlib.sha256(existing).hexdigest() != digest:
                raise ValueError("预览缓存校验失败")
            destination.chmod(0o600)
            return str(destination)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as image_file:
                image_file.write(data)
                image_file.flush()
            if not hasattr(os, "fchmod"):
                destination.chmod(0o600)
            return str(destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            os.close(fd)


def _decode_cover_responses(covers):
    if not isinstance(covers, list) or len(covers) > 5:
        raise ValueError("covers 响应无效")
    sanitized = []
    decoded = []
    for cover in covers:
        allowed = {"release_id", "cover_id", "cover_sha256", "video_sha256", "source", "time", "previews"}
        required = {"release_id", "cover_id", "cover_sha256", "video_sha256", "source", "previews"}
        if (
            not isinstance(cover, dict)
            or not required <= set(cover)
            or not set(cover) <= allowed
            or not _valid_release_id(cover.get("release_id"))
            or any(
                not isinstance(cover.get(field), str) or not _SHA256_RE.fullmatch(cover[field])
                for field in ("cover_id", "cover_sha256", "video_sha256")
            )
            or not isinstance(cover.get("source"), str)
            or not cover["source"]
            or ("time" in cover and (
                isinstance(cover["time"], bool)
                or not isinstance(cover["time"], (int, float))
                or not math.isfinite(cover["time"])
                or cover["time"] < 0
            ))
        ):
            raise ValueError("cover 响应无效")
        previews = cover.get("previews")
        if not isinstance(previews, list) or len(previews) != 2:
            raise ValueError("预览响应无效")
        sanitized_previews = []
        seen_formats = set()
        for preview in previews:
            if (
                not isinstance(preview, dict)
                or set(preview) != {"format", "jpeg_base64"}
                or not isinstance(preview.get("format"), str)
                or preview.get("format") not in {"landscape", "portrait"}
                or preview["format"] in seen_formats
                or not isinstance(preview.get("jpeg_base64"), str)
                or len(preview["jpeg_base64"]) > (_MAX_COVER_PREVIEW_BYTES * 4 // 3 + 4)
            ):
                raise ValueError("JPEG 预览响应无效")
            try:
                image_data = base64.b64decode(preview["jpeg_base64"], validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("JPEG 预览编码无效") from exc
            if (
                not image_data
                or len(image_data) > _MAX_COVER_PREVIEW_BYTES
                or not image_data.startswith(b"\xff\xd8\xff")
                or not image_data.endswith(b"\xff\xd9")
            ):
                raise ValueError("JPEG 预览格式或大小无效")
            _validate_cover_preview_jpeg(image_data, preview["format"])
            seen_formats.add(preview["format"])
            sanitized_previews.append({"format": preview["format"]})
            decoded.append((cover["cover_id"], preview["format"], image_data))
        if seen_formats != {"landscape", "portrait"}:
            raise ValueError("预览格式不完整")
        clean_cover = {key: value for key, value in cover.items() if key != "previews"}
        clean_cover["previews"] = sanitized_previews
        sanitized.append(clean_cover)
    return sanitized, decoded


def _looks_like_base64(value):
    if len(value) < 8 or len(value) % 4 or not re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", value):
        return False
    try:
        return len(base64.b64decode(value, validate=True)) >= 16
    except (binascii.Error, ValueError):
        return False


def _validate_cover_preview_jpeg(image_data, format_name):
    expected_size = _COVER_PREVIEW_SIZES[format_name]
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("无法加载 JPEG 解码器") from exc
    try:
        with Image.open(io.BytesIO(image_data), formats=("JPEG",)) as image:
            width, height = image.size
            if (
                image.format != "JPEG"
                or bool(getattr(image, "is_animated", False))
                or getattr(image, "n_frames", 1) != 1
                or width * height > _MAX_COVER_PREVIEW_PIXELS
                or image.size != expected_size
            ):
                raise ValueError("JPEG 预览尺寸或帧数无效")
            image.load()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError("JPEG 预览无法安全解码") from exc


def _validate_content_response(result, *, action=None):
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
    if "cover" in result and (action != "cover_import" or not isinstance(result["cover"], dict)):
        raise ValueError("意外的 cover 响应")
    if "cover_sources" in result and (
        not isinstance(result["cover_sources"], list)
        or any(not isinstance(item, dict) for item in result["cover_sources"])
    ):
        raise ValueError("cover_sources 响应无效")

    sanitized_covers = None
    sanitized_cover = None
    decoded_previews = []
    if "covers" in result:
        if action != "covers":
            raise ValueError("意外的 covers 响应")
        sanitized_covers, decoded_previews = _decode_cover_responses(result["covers"])
        result_to_scan = dict(result)
        result_to_scan["covers"] = sanitized_covers
    elif "cover" in result:
        sanitized_single, decoded_previews = _decode_cover_responses([result["cover"]])
        sanitized_cover = sanitized_single[0]
        result_to_scan = dict(result)
        result_to_scan["cover"] = sanitized_cover
    else:
        result_to_scan = result

    pending = [(result_to_scan, None)]
    while pending:
        value, field_name = pending.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = key.lower()
                if any(fragment in normalized_key for fragment in ("cookie", "base64", "path")):
                    raise ValueError("响应包含禁止字段")
                pending.append((child, normalized_key))
        elif isinstance(value, list):
            pending.extend((child, field_name) for child in value)
        elif isinstance(value, str) and (
            _COOKIE_VALUE_RE.search(value)
            or value.lower().startswith("file://")
            or _ABSOLUTE_PATH_RE.search(_PUBLIC_URL_RE.sub("", value))
            or _BASE64_VALUE_RE.fullmatch(value)
            or (
                field_name not in {
                    "release_id", "job_id", "image_id", "cover_id", "cover_sha256", "video_sha256", "token"
                }
                and _looks_like_base64(value)
            )
        ):
            raise ValueError("响应包含禁止内容")
    if sanitized_covers is not None:
        result = dict(result)
        result["covers"] = sanitized_covers
    if sanitized_cover is not None:
        result = dict(result)
        result["cover"] = sanitized_cover
    if decoded_previews:
        if not isinstance(result, dict):
            result = dict(result)
        media_tags = []
        with _COVER_CACHE_LOCK:
            protected_names = set()
            for cover_id, format_name, image_data in decoded_previews:
                path = _save_cover_preview(image_data)
                protected_names.add(Path(path).name)
                media_tags.append({
                    "cover_id": cover_id,
                    "format": format_name,
                    "media_tag": f"MEDIA:{path}",
                })
            _prune_cover_cache(protected_names)
        if media_tags:
            result["media_tags"] = media_tags
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
            return _validate_content_response(result, action=payload.get("action"))
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


def _inbound_now():
    return time.monotonic()


def _purge_inbound_images_locked(now):
    for image_id, record in list(_INBOUND_IMAGES.items()):
        if record["expires_at"] <= now:
            _INBOUND_IMAGES.pop(image_id, None)
    for nonce_key, expires_at in list(_INBOUND_IMAGE_NONCES.items()):
        if expires_at <= now:
            _INBOUND_IMAGE_NONCES.pop(nonce_key, None)
    while len(_INBOUND_IMAGES) > _MAX_INBOUND_IMAGES:
        _INBOUND_IMAGES.pop(next(iter(_INBOUND_IMAGES)))
    while len(_INBOUND_IMAGE_NONCES) > _MAX_INBOUND_NONCES:
        _INBOUND_IMAGE_NONCES.pop(next(iter(_INBOUND_IMAGE_NONCES)))


def _observe_inbound_images(event=None):
    if event is None or bool(getattr(event, "internal", False)):
        return None
    scope = _confirmation_scope(getattr(event, "source", None))
    nonce = getattr(event, "message_id", None)
    urls = getattr(event, "media_urls", None)
    media_types = getattr(event, "media_types", None)
    if (
        scope is None
        or not isinstance(nonce, str)
        or not nonce
        or len(nonce) > 256
        or not isinstance(urls, list)
        or not isinstance(media_types, list)
        or len(urls) != len(media_types)
    ):
        return None

    mime_extensions = {
        "image/jpeg": {".jpg", ".jpeg"},
        "image/jpg": {".jpg", ".jpeg"},
        "image/png": {".png"},
        "image/webp": {".webp"},
    }
    candidates = []
    for ordinal, (url, media_type) in enumerate(zip(urls, media_types), start=1):
        if not isinstance(media_type, str):
            continue
        mime = media_type.split(";", 1)[0].strip().lower()
        path = _inbound_image_path(url)
        if path is None or path.suffix.lower() not in mime_extensions.get(mime, set()):
            continue
        candidates.append((ordinal, str(path)))
    if not candidates:
        return None

    now = _inbound_now()
    received_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    nonce_key = (scope, nonce)
    with _INBOUND_IMAGE_LOCK:
        _purge_inbound_images_locked(now)
        if nonce_key in _INBOUND_IMAGE_NONCES:
            return None
        _INBOUND_IMAGE_NONCES[nonce_key] = now + _INBOUND_IMAGE_TTL
        for ordinal, path in candidates:
            image_id = secrets.token_hex(16)
            while image_id in _INBOUND_IMAGES:
                image_id = secrets.token_hex(16)
            _INBOUND_IMAGES[image_id] = {
                "scope": scope,
                "message_nonce": nonce,
                "path": path,
                "ordinal": ordinal,
                "received_at": received_at,
                "received_monotonic": now,
                "expires_at": now + _INBOUND_IMAGE_TTL,
            }
            while len(_INBOUND_IMAGES) > _MAX_INBOUND_IMAGES:
                _INBOUND_IMAGES.pop(next(iter(_INBOUND_IMAGES)))
        while len(_INBOUND_IMAGE_NONCES) > _MAX_INBOUND_NONCES:
            _INBOUND_IMAGE_NONCES.pop(next(iter(_INBOUND_IMAGE_NONCES)))
    return None


def _cover_sources(scope):
    now = _inbound_now()
    with _INBOUND_IMAGE_LOCK:
        _purge_inbound_images_locked(now)
        records = [dict(record, image_id=image_id) for image_id, record in _INBOUND_IMAGES.items() if record["scope"] == scope]

    valid = []
    invalid_ids = []
    for record in records:
        if _inbound_image_path(record["path"]) is None:
            invalid_ids.append(record["image_id"])
            continue
        valid.append({
            "image_id": record["image_id"],
            "received_at": record["received_at"],
            "ordinal": record["ordinal"],
            "received_monotonic": record["received_monotonic"],
        })
    if invalid_ids:
        with _INBOUND_IMAGE_LOCK:
            for image_id in invalid_ids:
                _INBOUND_IMAGES.pop(image_id, None)
    valid.sort(key=lambda record: (-record["received_monotonic"], record["ordinal"]))
    for record in valid:
        record.pop("received_monotonic", None)
    return valid


def _read_registered_image(image_id, scope):
    with _INBOUND_IMAGE_LOCK:
        now = _inbound_now()
        _purge_inbound_images_locked(now)
        record = _INBOUND_IMAGES.get(image_id)
        record = dict(record) if record is not None else None
    if record is None or record["scope"] != scope:
        raise ValueError("图片来源已过期或不可用")
    path = _inbound_image_path(record["path"])
    if path is None:
        raise ValueError("图片来源已过期或不可用")
    data = _read_no_follow(path, _MAX_INBOUND_IMAGE_BYTES)
    if not data:
        raise ValueError("图片内容为空")
    return data


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
    _observe_inbound_images(event)
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
    owner_scope = _owner_qq_dm_scope() if action in {"cover_sources", "cover_import"} else None
    if action in {"cover_sources", "cover_import"} and owner_scope is None:
        return json.dumps({"ok": False, "state": "unavailable", "message": "封面图片来源仅可在指定 QQ 私聊中查看或导入。"}, ensure_ascii=False)
    if action not in {"cover_sources", "cover_import"} and not _authorized():
        return json.dumps({"ok": False, "state": "unavailable", "message": "仅指定账号的 QQ 私聊或本机运维可用。"}, ensure_ascii=False)
    if action == "cover_sources":
        result = {
            "ok": True,
            "state": "ready",
            "message": "仅列出最近收到的 QQ 私聊图片候选；请选择图片后再导入。",
            "cover_sources": _cover_sources(owner_scope),
        }
        return json.dumps(result, ensure_ascii=False)
    if action == "publish" and not _consume_publish_confirmation(args["token"]):
        return json.dumps({"ok": False, "state": "needs_attention", "message": "公开发布需先在指定 QQ 私聊发送完整确认命令；本次操作已拒绝。"}, ensure_ascii=False)
    try:
        request = args
        if action == "cover_import":
            try:
                image_data = _read_registered_image(args["image_id"], owner_scope)
            except (OSError, ValueError):
                return json.dumps({
                    "ok": False,
                    "state": "needs_attention",
                    "message": "这张图片来源已过期或不可用；请重新在指定 QQ 私聊发送图片。",
                }, ensure_ascii=False)
            request = {
                "action": "cover_import",
                "release_id": args["release_id"],
                "image_base64": base64.b64encode(image_data).decode("ascii"),
            }
        result = await _request_content(request)
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
                "管理抖音作品。先用 list 选择服务器上的成品；用 covers 查看视频帧，或在指定 QQ 私聊中用 cover_sources 列候选图片、"
                "再按 image_id 调用 cover_import。把候选 MEDIA 预览给用户并等待其明确选择 cover_id，禁止自行选封面。"
                "用户选择后用 prepare（必须传该 cover_id）确认标题、简介、封面、可见范围和可选定时；若用户要求暂存则调用 draft。"
                "需要发布时用 stage 上传并生成平台待确认预览。stage/job 返回 editor_ready 仅表示预览已就绪，绝不代替用户点击保存或发布；用户要求保存草稿时调用 draft，同一有效 stage token 会保存当前预览，否则按草稿流程上传。"
                "此预览最长有效 15 分钟。stage 后不要调用 login/status/metrics 或另一次 prepare，因为这些操作会导航并使预览失效；job 查询不会导航。"
                "只有收到指定 QQ 私聊中的真实用户消息“确认发布 <token>”后，才可调用 publish；不得依据模型参数、confirmed 字段或预览自行发布。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "metrics", "covers", "cover_sources", "cover_import", "prepare", "stage", "draft", "job", "publish"]},
                    "release_id": {"type": "string"},
                    "image_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
                    "times": {"type": "array", "maxItems": 5, "items": {"type": "number", "minimum": 0}},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "cover_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "visibility": {"type": "string", "enum": ["public", "friends", "private"]},
                    "publish_at": {"type": "string", "format": "date-time"},
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
