"""通过本机受限套接字访问独立抖音登录服务。"""

import asyncio
import base64
import binascii
import errno
import hashlib
import io
import json
import logging
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
    "covers", "cover_sources", "saved_sources", "cover", "recovery", "total", "next_offset", "verification_submitted",
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
_SAVED_COVER_VARIANTS = (("9x16", "9:16"), ("16x9", "16:9"), ("4x3", "4:3"), ("3x4", "3:4"))
_SAVED_COVER_EXTENSIONS = (("png", "PNG"), ("jpg", "JPEG"), ("jpeg", "JPEG"), ("webp", "WEBP"))
_SAVED_COVER_ASPECTS = {"9:16": (9, 16), "16:9": (16, 9), "4:3": (4, 3), "3:4": (3, 4)}
_COVER_SOURCES = {"qq_image", "video_frame", "library_image", "saved_image", "paired_images"}
_INBOUND_IMAGE_LOCK = threading.Lock()
_INBOUND_IMAGES = {}
_INBOUND_IMAGE_NONCES = {}
_COVER_CACHE_LOCK = threading.RLock()
_VERIFICATION_LOCK = threading.Lock()
_VERIFICATIONS = {}
_VERIFICATION_MESSAGES = {}
_VERIFICATION_TASKS = set()
_VERIFICATION_TTL = 5 * 60
_VERIFICATION_COOLDOWN = 60
_VERIFICATION_LOGGER = logging.getLogger("douyin_verification")


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


async def _request(action, *, recovery=False):
    async with asyncio.timeout(50):
        for attempt in range(2):
            try:
                return await _request_once(action, recovery=recovery)
            except OSError:
                if attempt:
                    raise
                await asyncio.sleep(0.5)


async def _request_once(action, *, recovery=False):
    writer = None
    try:
        async with asyncio.timeout(50):
            reader, writer = await asyncio.open_unix_connection(
                os.environ.get("DOUYIN_LOGIN_SOCKET", SOCKET_PATH),
                limit=MAX_RESPONSE,
            )
            payload = {"action": action}
            if recovery:
                payload["recover"] = True
            writer.write(json.dumps(payload).encode() + b"\n")
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
        and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value, re.ASCII) is not None
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
            or not 1 <= len(args["times"]) <= 5
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 1e12
                or not math.isfinite(value)
                for value in args["times"]
            )
        ):
            raise ValueError("times 必须是最多五个非负有限秒数")
    elif action == "cover_sources":
        if set(args) != {"action"}:
            raise ValueError("cover_sources 仅接受 action")
    elif action == "cover_saved_sources":
        if set(args) != {"action", "release_id"} or not _valid_release_id(args.get("release_id")):
            raise ValueError("cover_saved_sources 字段无效")
    elif action == "cover_library":
        if not set(args) <= {"action", "release_id", "offset"}:
            raise ValueError("cover_library 字段无效")
        if "release_id" in args and not _valid_release_id(args["release_id"]):
            raise ValueError("release_id 无效")
        if "offset" in args and (type(args["offset"]) is not int or not 0 <= args["offset"] <= 10000):
            raise ValueError("图库分页偏移无效")
    elif action == "cover_reuse":
        if set(args) != {"action", "release_id", "from_release_id", "cover_id"}:
            raise ValueError("cover_reuse 字段无效")
        if any(not _valid_release_id(args[k]) for k in ("release_id", "from_release_id")):
            raise ValueError("作品编号无效")
        if not isinstance(args["cover_id"], str) or not _SHA256_RE.fullmatch(args["cover_id"]):
            raise ValueError("封面编号无效")
    elif action == "cover_import":
        if set(args) != {"action", "release_id", "image_id"}:
            raise ValueError("cover_import 字段无效")
        if not _valid_release_id(args.get("release_id")):
            raise ValueError("release_id 无效")
        if not isinstance(args.get("image_id"), str) or not _IMAGE_ID_RE.fullmatch(args["image_id"]):
            raise ValueError("image_id 无效")
    elif action == "cover_import_saved":
        if set(args) != {"action", "release_id", "image_id"}:
            raise ValueError("cover_import_saved 字段无效")
        if not _valid_release_id(args.get("release_id")):
            raise ValueError("release_id 无效")
        if not isinstance(args.get("image_id"), str) or not _IMAGE_ID_RE.fullmatch(args["image_id"]):
            raise ValueError("image_id 无效")
    elif action == "cover_pair":
        if not {"action", "release_id", "landscape_cover_id", "portrait_cover_id"} <= set(args) or not set(args) <= {
            "action", "release_id", "landscape_cover_id", "portrait_cover_id", "from_release_id"
        }:
            raise ValueError("cover_pair 字段无效")
        if not _valid_release_id(args.get("release_id")):
            raise ValueError("release_id 无效")
        if "from_release_id" in args and not _valid_release_id(args["from_release_id"]):
            raise ValueError("from_release_id 无效")
        if any(
            not isinstance(args.get(field), str) or not _SHA256_RE.fullmatch(args[field])
            for field in ("landscape_cover_id", "portrait_cover_id")
        ):
            raise ValueError("单图封面编号无效")
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
    elif action in {"stage", "resume_stage", "draft", "publish"}:
        references = set(args) & {"plan_id", "token"}
        if action == "publish" and set(args) == {"action"}:
            pass
        elif len(references) != 1 or set(args) != {"action"} | references:
            raise ValueError("只接受一个完整的 plan_id")
        else:
            value = args[next(iter(references))]
            if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
                raise ValueError("plan_id 无效")
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


def _decode_cover_responses(covers, *, expected_source=None):
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
            or cover["source"] not in _COVER_SOURCES
            or (expected_source is not None and cover["source"] != expected_source)
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
    if "verification_submitted" in result and (
        action != "verification_submit" or result["verification_submitted"] is not True
        or result["state"] != "in_progress"
    ):
        raise ValueError("无效验证码提交回执")
    if "recovery" in result and (
        not isinstance(result["recovery"], dict)
        or set(result["recovery"]) != {"action"}
        or not isinstance(result["recovery"]["action"], str)
        or result["recovery"]["action"] not in {
            "login", "manual_verification", "check_account", "check_status", "maintenance", "inspect_result", "resume_stage", "prepare"
        }
    ):
        raise ValueError("无效恢复指引")
    if "releases" in result and (
        not isinstance(result["releases"], list)
        or any(not isinstance(item, dict) for item in result["releases"])
    ):
        raise ValueError("releases 响应无效")
    for field in ("plan", "job", "metrics", "ui"):
        if field in result and not isinstance(result[field], dict):
            raise ValueError(f"{field} 响应无效")
    if "cover" in result and (
        action not in {"cover_import", "cover_import_saved", "cover_reuse", "cover_pair"}
        or not isinstance(result["cover"], dict)
    ):
        raise ValueError("意外的 cover 响应")
    if any(k in result for k in ("total", "next_offset")):
        if (action != "cover_library" or type(result.get("total")) is not int or result["total"] < 0
                or (result.get("next_offset") is not None and (
                    type(result["next_offset"]) is not int or not 0 <= result["next_offset"] <= result["total"]))):
            raise ValueError("图库分页响应无效")
    if "cover_sources" in result and (
        not isinstance(result["cover_sources"], list)
        or any(not isinstance(item, dict) for item in result["cover_sources"])
    ):
        raise ValueError("cover_sources 响应无效")
    if "saved_sources" in result:
        saved_sources = result["saved_sources"]
        if action != "cover_saved_sources" or not isinstance(saved_sources, list) or len(saved_sources) > 16:
            raise ValueError("saved_sources 响应无效")
        expected_fields = {
            "image_id", "filename", "release_id", "width", "height", "aspect", "expected_aspect",
        }
        seen_image_ids = set()
        for source in saved_sources:
            if (
                not isinstance(source, dict)
                or set(source) != expected_fields
                or not isinstance(source.get("image_id"), str)
                or not _IMAGE_ID_RE.fullmatch(source["image_id"])
                or source["image_id"] in seen_image_ids
                or not _valid_release_id(source.get("release_id"))
                or not isinstance(source.get("filename"), str)
                or "/" in source["filename"]
                or "\\" in source["filename"]
                or Path(source["filename"]).name != source["filename"]
                or not re.fullmatch(
                    re.escape(source["release_id"])
                    + r"_(?:9x16|16x9|4x3|3x4)\.(?:png|jpg|jpeg|webp)",
                    source["filename"],
                )
                or type(source.get("width")) is not int
                or type(source.get("height")) is not int
                or source["width"] <= 0
                or source["height"] <= 0
                or source["width"] * source["height"] > _MAX_COVER_PREVIEW_PIXELS
                or not isinstance(source.get("aspect"), str)
                or source["aspect"] not in _SAVED_COVER_ASPECTS
                or not isinstance(source.get("expected_aspect"), str)
                or source["expected_aspect"] not in _SAVED_COVER_ASPECTS
                or not any(
                    source["width"] * aspect_height == source["height"] * aspect_width
                    and aspect == source["aspect"]
                    for aspect, (aspect_width, aspect_height) in _SAVED_COVER_ASPECTS.items()
                )
                or _SAVED_COVER_VARIANTS[
                    next(
                        index for index, (variant, _aspect) in enumerate(_SAVED_COVER_VARIANTS)
                        if f"_{variant}." in source["filename"]
                    )
                ][1] != source["expected_aspect"]
            ):
                raise ValueError("saved_sources 项目无效")
            seen_image_ids.add(source["image_id"])

    sanitized_covers = None
    sanitized_cover = None
    decoded_previews = []
    if "covers" in result:
        if action not in {"covers", "cover_library"}:
            raise ValueError("意外的 covers 响应")
        sanitized_covers, decoded_previews = _decode_cover_responses(result["covers"])
        result_to_scan = dict(result)
        result_to_scan["covers"] = sanitized_covers
    elif "cover" in result:
        expected_source = "paired_images" if action == "cover_pair" else None
        sanitized_single, decoded_previews = _decode_cover_responses(
            [result["cover"]], expected_source=expected_source,
        )
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
    if payload.get("action") not in {"list", "job"}:
        return await _request_content_once(payload)
    async with asyncio.timeout(50):
        for attempt in range(2):
            try:
                return await _request_content_once(payload)
            except OSError:
                if attempt:
                    raise
                await asyncio.sleep(0.5)


async def _request_content_once(payload):
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


def _saved_cover_root(root=None):
    return Path(root) if root is not None else Path.home() / "workspace" / "starlibrary_covers"


def _saved_file_stat_identity(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _saved_directory_snapshot(path):
    absolute = Path(os.path.abspath(os.fspath(path)))
    _checked_directory(absolute)
    components = [Path(absolute.anchor)]
    current = components[0]
    for part in absolute.parts[1:]:
        current = current / part
        components.append(current)
    snapshot = []
    for component in components:
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("不安全的制作素材目录")
        snapshot.append((component, info.st_dev, info.st_ino))
    return tuple(snapshot)


def _verify_saved_directory_snapshot(snapshot):
    for component, device, inode in snapshot:
        info = component.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or (info.st_dev, info.st_ino) != (device, inode)
        ):
            raise ValueError("制作素材目录身份已变化")


def _saved_directory_open_flags():
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("当前系统不支持安全的本地素材目录读取")
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_saved_cover_directory(path):
    absolute = Path(os.path.abspath(os.fspath(path)))
    flags = _saved_directory_open_flags()
    directory_fd = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except FileNotFoundError:
        os.close(directory_fd)
        raise
    except OSError as exc:
        os.close(directory_fd)
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError("不安全的制作素材目录") from exc
        raise


def _open_saved_cover_child_directory(parent_fd, name):
    try:
        return os.open(name, _saved_directory_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError("不安全的制作素材目录") from exc
        raise


def _read_saved_cover_file_posix(directory_fd, filename, max_bytes):
    before = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("制作素材必须是普通文件")
    if before.st_size > max_bytes:
        raise ValueError("制作素材超过大小限制")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(filename, flags, dir_fd=directory_fd)
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or _saved_file_stat_identity(before) != _saved_file_stat_identity(opened)
        ):
            raise ValueError("制作素材文件身份已变化")
        if opened.st_size > max_bytes:
            raise ValueError("制作素材超过大小限制")

        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(fd, min(64 * 1024, max_bytes + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > max_bytes:
            raise ValueError("制作素材超过大小限制")

        after = os.fstat(fd)
        named_after = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(named_after.st_mode)
            or _saved_file_stat_identity(before) != _saved_file_stat_identity(opened)
            or _saved_file_stat_identity(opened) != _saved_file_stat_identity(after)
            or _saved_file_stat_identity(after) != _saved_file_stat_identity(named_after)
            or len(data) != after.st_size
        ):
            raise ValueError("制作素材文件身份或内容已变化")
        return bytes(data)
    finally:
        os.close(fd)


def _read_saved_cover_file_windows(path, directory_snapshot, max_bytes):
    _verify_saved_directory_snapshot(directory_snapshot)
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("制作素材必须是普通文件")
    if before.st_size > max_bytes:
        raise ValueError("制作素材超过大小限制")
    data = _read_no_follow(path, max_bytes)
    after = path.lstat()
    _verify_saved_directory_snapshot(directory_snapshot)
    if (
        stat.S_ISLNK(after.st_mode)
        or not stat.S_ISREG(after.st_mode)
        or _saved_file_stat_identity(before) != _saved_file_stat_identity(after)
        or len(data) != after.st_size
    ):
        raise ValueError("制作素材文件身份或内容已变化")
    return data


def _read_saved_cover_records(directory, scope, release_id, *, posix_fd, directory_snapshot=None):
    scope_parts = scope if isinstance(scope, (tuple, list)) else (scope or "owner",)
    records = []
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("无法加载图片解码器") from exc

    for variant, expected_aspect in _SAVED_COVER_VARIANTS:
        for extension, expected_format in _SAVED_COVER_EXTENSIONS:
            filename = f"{release_id}_{variant}.{extension}"
            try:
                if posix_fd:
                    data = _read_saved_cover_file_posix(directory, filename, _MAX_INBOUND_IMAGE_BYTES)
                else:
                    data = _read_saved_cover_file_windows(
                        directory / filename, directory_snapshot, _MAX_INBOUND_IMAGE_BYTES,
                    )
            except FileNotFoundError:
                continue
            try:
                with Image.open(io.BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as image:
                    width, height = image.size
                    actual_aspect = next((
                        aspect for aspect, (aspect_width, aspect_height) in _SAVED_COVER_ASPECTS.items()
                        if width * aspect_height == height * aspect_width
                    ), None)
                    if (
                        image.format != expected_format
                        or bool(getattr(image, "is_animated", False))
                        or getattr(image, "n_frames", 1) != 1
                        or width <= 0
                        or height <= 0
                        or width * height > _MAX_COVER_PREVIEW_PIXELS
                        or actual_aspect is None
                    ):
                        raise ValueError("制作素材图片尺寸、比例或帧数无效")
                    image.load()
            except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
                raise ValueError("制作素材图片无法安全解码") from exc

            content_sha256 = hashlib.sha256(data).hexdigest()
            identity = hashlib.sha256("\0".join((
                *(str(part) for part in scope_parts), release_id, filename, content_sha256,
            )).encode("utf-8")).hexdigest()[:32]
            records.append(({
                "image_id": identity,
                "filename": filename,
                "release_id": release_id,
                "width": width,
                "height": height,
                "aspect": actual_aspect,
                "expected_aspect": expected_aspect,
            }, data))
    return records


def _enumerate_saved_cover_sources(release_id, scope, root=None):
    if not _valid_release_id(release_id):
        raise ValueError("作品编号无效")
    root_path = _saved_cover_root(root)
    if os.name == "posix":
        try:
            root_fd = _open_saved_cover_directory(root_path)
        except FileNotFoundError:
            return False, []
        try:
            try:
                release_fd = _open_saved_cover_child_directory(root_fd, release_id)
            except FileNotFoundError:
                return True, []
            try:
                return True, _read_saved_cover_records(
                    release_fd, scope, release_id, posix_fd=True,
                )
            finally:
                os.close(release_fd)
        finally:
            os.close(root_fd)

    # Windows 保留目录链检查并比较读取前后的身份快照；该路径 API 不提供 POSIX dirfd 的等价保证。
    try:
        checked_root = _checked_directory(root_path)
    except FileNotFoundError:
        return False, []
    try:
        release_directory = _checked_directory(checked_root / release_id)
    except FileNotFoundError:
        return True, []
    directory_snapshot = _saved_directory_snapshot(release_directory)
    return True, _read_saved_cover_records(
        release_directory, scope, release_id, posix_fd=False,
        directory_snapshot=directory_snapshot,
    )


def _saved_cover_sources(release_id, scope, root=None):
    _delivered, records = _enumerate_saved_cover_sources(release_id, scope, root)
    return [record for record, _data in records]


def _read_saved_cover_image(image_id, release_id, scope, root=None):
    if not isinstance(image_id, str) or not _IMAGE_ID_RE.fullmatch(image_id):
        raise ValueError("图片编号无效")
    _delivered, records = _enumerate_saved_cover_sources(release_id, scope, root)
    for record, data in records:
        if record["image_id"] == image_id:
            return data
    raise ValueError("制作素材已变更或不可用")


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
    if not isinstance(nonce, str) or not nonce:
        return None

    now = time.monotonic()
    deadline = now + _CONFIRMATION_TTL
    nonce_key = (scope, nonce)
    with _CONFIRMATION_LOCK:
        _purge_confirmations(now)
        if nonce_key in _CONFIRMATION_NONCES:
            return None
        _CONFIRMATION_NONCES[nonce_key] = now + _CONFIRMATION_NONCE_TTL
        # 本人后续消息会撤销旧意图；重放旧消息不能恢复或延长授权。
        for key in list(_CONFIRMATIONS):
            if key[0] == scope:
                _CONFIRMATIONS.pop(key, None)
        if not match:
            return None
        token_key = (scope, match.group(1))
        if token_key in _USED_CONFIRMATION_TOKENS:
            return None
        _CONFIRMATIONS[token_key] = (deadline, nonce)
    return None


def _take_publish_confirmation(plan_id=None):
    """只从当前可信 QQ 消息取一次确认码，不让模型搬运敏感参数。"""
    from gateway.session_context import get_session_env

    scope = _owner_qq_dm_scope()
    message_id = get_session_env("HERMES_SESSION_MESSAGE_ID", "")
    if scope is None or not isinstance(message_id, str) or not message_id:
        return None
    now = time.monotonic()
    with _CONFIRMATION_LOCK:
        _purge_confirmations(now)
        matches = [
            key for key, (deadline, nonce) in _CONFIRMATIONS.items()
            if key[0] == scope and nonce == message_id and deadline > now
            and (plan_id is None or key[1] == plan_id)
        ]
        if len(matches) != 1:
            return None
        key = matches[0]
        _CONFIRMATIONS.pop(key)
        _USED_CONFIRMATION_TOKENS[key] = now + _CONFIRMATION_TTL
        return key[1]


def _consume_publish_confirmation(token):
    """兼容既有内部调用；同样校验当前 QQ 消息。"""
    return _take_publish_confirmation(token) is not None


async def handle_content(args, **kwargs):
    try:
        action = _content_payload(args)
    except ValueError:
        return json.dumps({"ok": False, "state": "needs_attention", "message": (
            "内容操作参数无效；未执行任何操作。stage/draft 使用 prepare 返回的完整 plan_id；"
            "收到本人确认后，publish 仅传 action，不复制 token、星号或缩略值，不重复相同错误调用。"
        )}, ensure_ascii=False)
    owner_actions = {
        "cover_sources", "cover_import", "cover_saved_sources", "cover_import_saved",
        "cover_pair", "cover_library", "cover_reuse",
    }
    owner_scope = _owner_qq_dm_scope() if action in owner_actions else None
    if action in owner_actions and owner_scope is None:
        return json.dumps({"ok": False, "state": "unavailable", "message": "封面库与图片来源仅可在指定 QQ 私聊中查看、导入或复用。"}, ensure_ascii=False)
    if action not in owner_actions and not _authorized():
        return json.dumps({"ok": False, "state": "unavailable", "message": "仅指定账号的 QQ 私聊或本机运维可用。"}, ensure_ascii=False)
    if action == "cover_sources":
        result = {
            "ok": True,
            "state": "ready",
            "message": "仅列出最近收到的 QQ 私聊图片候选；请选择图片后再导入。",
            "cover_sources": _cover_sources(owner_scope),
        }
        return json.dumps(result, ensure_ascii=False)
    if action == "cover_saved_sources":
        try:
            delivered, records = _enumerate_saved_cover_sources(
                args["release_id"], owner_scope,
            )
        except (OSError, ValueError):
            return json.dumps({
                "ok": False,
                "state": "needs_attention",
                "message": "固定制作目录或素材不安全、无效；请检查该作品目录中的规范图片文件。",
                "saved_sources": [],
            }, ensure_ascii=False)
        saved_sources = [record for record, _data in records]
        if not delivered:
            message = "固定制作目录尚未交付，因此没有可列出的本地封面素材。"
        elif saved_sources:
            message = "已列出该作品固定制作目录中的规范图片素材；image_id 只标识当前文件内容。"
        else:
            message = "该作品目录中没有符合命名、尺寸和比例要求的本地封面素材。"
        return json.dumps({
            "ok": True,
            "state": "ready",
            "message": message,
            "saved_sources": saved_sources,
        }, ensure_ascii=False)
    request = args
    if action in {"stage", "resume_stage", "draft"}:
        request = {"action": action, "token": args.get("plan_id", args.get("token"))}
    elif action == "publish":
        token = _take_publish_confirmation(args.get("plan_id", args.get("token")))
        if token is None:
            return json.dumps({"ok": False, "state": "needs_attention", "message": "公开发布需由当前指定 QQ 私聊消息发送完整确认命令；本次操作已拒绝。"}, ensure_ascii=False)
        request = {"action": action, "token": token}
    try:
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
        elif action == "cover_import_saved":
            try:
                image_data = _read_saved_cover_image(
                    args["image_id"], args["release_id"], owner_scope,
                )
            except (OSError, ValueError):
                return json.dumps({
                    "ok": False,
                    "state": "needs_attention",
                    "message": "该制作素材已变更或不可用；请重新查看 cover_saved_sources。",
                }, ensure_ascii=False)
            request = {
                "action": "cover_import_saved",
                "release_id": args["release_id"],
                "image_base64": base64.b64encode(image_data).decode("ascii"),
            }
        result = await _request_content(request)
        if action == "prepare" and isinstance(result.get("plan"), dict):
            reference = result["plan"].get("token")
            if not isinstance(reference, str) or not _TOKEN_RE.fullmatch(reference):
                raise ValueError("准备响应缺少有效计划引用")
            # 模型只看稳定引用；内部协议继续用 token，避免两个字段被脱敏成不同值。
            plan = {key: value for key, value in result["plan"].items() if key != "token"}
            result = {**result, "plan": {**plan, "plan_id": reference}}
        if (action in {"prepare", "metrics", "job"} and _owner_qq_dm_scope() is not None
                and result.get("state") == "login_required"
                and result.get("recovery") == {"action": "login"}):
            try:
                result["login"] = await _login_response("login", recovery=True)
            except (OSError, ValueError, binascii.Error, asyncio.TimeoutError):
                result["login"] = {"ok": False, "state": "unavailable", "message": "未能取得登录二维码；请检查状态，不重提作品。"}
            result["recovery_instruction"] = (
                "优先向本人说明 login 的当前状态；有二维码时发到本次私聊。扫码后检查登录状态，"
                "重新准备并核对作品；旧编辑预览和发布确认不沿用，不自动重新上传或发布。"
            )
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
    root = _checked_directory(Path(get_hermes_home()) / "cache" / "douyin-login", create=True, private=True)
    for old in root.glob("qr-*.png"):
        info = old.lstat()
        if stat.S_ISREG(info.st_mode) and time.time() - info.st_mtime > 600:
            old.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile(prefix="qr-", suffix=".png", dir=root, delete=False) as f:
        f.write(data)
        path = Path(f.name)
    path.chmod(0o600)
    return str(path.resolve())


async def _login_response(action, *, recovery=False):
    result = await _request(action, recovery=True) if recovery else await _request(action)
    output = {key: result[key] for key in ("ok", "state", "message")}
    encoded = result.get("qr_png_base64")
    if encoded is not None:
        if action != "login" or result["state"] != "login_required":
            raise ValueError("意外二维码响应")
        path = _save_qr(encoded)
        output.update(
            media_tag=f"MEDIA:{path}",
            delivery_instruction="网关会把二维码自动附到本次指定私聊回复；说明用抖音手机端扫码即可，不转发其他会话，不展示缓存路径。",
        )
    return output


async def handle(args, **kwargs):
    if not isinstance(args, dict) or set(args) != {"action"} or not isinstance(args["action"], str) or args["action"] not in {"status", "login"}:
        return json.dumps({"ok": False, "state": "unavailable", "message": "仅支持 status 或 login。"}, ensure_ascii=False)
    if not _authorized():
        return json.dumps({"ok": False, "state": "unavailable", "message": "仅指定账号的 QQ 私聊或本机运维可用。"}, ensure_ascii=False)
    try:
        output = await _login_response(args["action"])
        return json.dumps(output, ensure_ascii=False)
    except (OSError, ValueError, binascii.Error, asyncio.TimeoutError):
        return json.dumps({"ok": False, "state": "unavailable", "message": "抖音登录服务暂不可用或响应无效；未修改现有登录数据。"}, ensure_ascii=False)


async def handle_verification(args, **kwargs):
    """只向模型开放发码，验证码本身由入站前置hook消费。"""
    scope = _owner_qq_dm_scope()
    if scope is None:
        return json.dumps({"ok": False, "state": "unavailable", "message": "发布短信验证仅可在指定本人QQ私聊中处理。"}, ensure_ascii=False)
    if not isinstance(args, dict) or set(args) != {"job_id"} or not isinstance(args["job_id"], str) or not _JOB_ID_RE.fullmatch(args["job_id"]):
        return json.dumps({"ok": False, "state": "needs_attention", "message": "请提供当前等待短信验证的完整发布任务编号；不要把验证码放进工具参数。"}, ensure_ascii=False)
    job_id = args["job_id"]
    now = time.monotonic()
    with _VERIFICATION_LOCK:
        pending = _VERIFICATIONS.get(scope)
        if pending and (pending.get("requesting") or pending.get("processing")):
            return json.dumps({"ok": False, "state": "needs_attention", "message": "当前短信验证请求仍在处理中，不要重复发送或提交。"}, ensure_ascii=False)
        if pending and pending["job_id"] == job_id and now - pending["requested_at"] < _VERIFICATION_COOLDOWN:
            if pending.get("sms_ready") and pending["expires_at"] > now:
                return json.dumps({"ok": True, "state": "ready", "message": "刚刚已请求短信验证码；请本人直接回复最新六位数字，不要反复请求发送。"}, ensure_ascii=False)
            return json.dumps({"ok": False, "state": "needs_attention", "message": "上次发码未确认或收码窗口已失效；请先查询原任务，稍后再按任务提示请求短信。"}, ensure_ascii=False)
        binding = {"job_id": job_id, "requested_at": now, "expires_at": now + _VERIFICATION_TTL, "requesting": True, "sms_ready": False, "processing": False}
        _VERIFICATIONS[scope] = binding
    try:
        result = await _request_content({"action": "verification_request_sms", "job_id": job_id})
        if result.get("state") != "ready" or result.get("job", {}).get("job_id") != job_id:
            with _VERIFICATION_LOCK:
                _VERIFICATIONS.pop(scope, None)
            return json.dumps(result, ensure_ascii=False)
        with _VERIFICATION_LOCK:
            if _VERIFICATIONS.get(scope) is binding:
                binding["requesting"] = False
                binding["sms_ready"] = True
        result = {**result, "message": "已向当前发布验证页面请求发送短信。请本人在本次QQ私聊键入纯文本六位数字，不加前缀，不用语音或图片；程序会代填并点击验证，该纯文本验证码不会进入模型、工具参数或会话记录。尚未确认发布成功。"}
        return json.dumps(result, ensure_ascii=False)
    except asyncio.CancelledError:
        with _VERIFICATION_LOCK:
            if _VERIFICATIONS.get(scope) is binding:
                binding.update(requesting=False, expires_at=0)
        raise
    except (OSError, ValueError, asyncio.TimeoutError):
        with _VERIFICATION_LOCK:
            _VERIFICATIONS.pop(scope, None)
        return json.dumps({"ok": False, "state": "unavailable", "message": "短信验证服务暂不可用；未自动重试，也未重新提交作品。"}, ensure_ascii=False)


async def _verification_notice(adapter, chat_id, message_id, text):
    try:
        await adapter._send_with_retry(chat_id=chat_id, content=text, reply_to=message_id)
    except Exception as exc:
        _VERIFICATION_LOGGER.warning("发布短信固定回执发送异常：%s", type(exc).__name__)


async def _deliver_verification(scope, job_id, code, adapter, chat_id, message_id):
    finished = False
    text = "验证码处理未确认完成；请查询原发布任务，不要重复发布或重新上传。"
    async def acknowledge():
        try:
            await adapter._send_with_retry(chat_id=chat_id, content="已安全接收本次发布验证码，正在处理原任务，不会重新上传或重复发布。", reply_to=message_id)
        except Exception as exc:
            _VERIFICATION_LOGGER.warning("发布短信接收回执发送异常：%s", type(exc).__name__)

    acknowledgement = asyncio.create_task(acknowledge())
    try:
        # 发码工具与入站hook可能分处不同线程；只在内存中等到发码已确认。
        deadline = time.monotonic() + 55
        while True:
            with _VERIFICATION_LOCK:
                binding = _VERIFICATIONS.get(scope)
                valid = bool(binding and binding["job_id"] == job_id and binding["expires_at"] > time.monotonic())
                requesting = bool(valid and binding.get("requesting"))
                ready = bool(valid and binding.get("sms_ready"))
            if not requesting or time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.05)
        if not ready:
            text = "发送短信尚未确认或收码窗口已失效，验证码未提交；请查询原任务，不要重复发布。"
            return
        result = await _request_content({"action": "verification_submit", "job_id": job_id, "code": code})
        code = None
        accepted = result.get("verification_submitted") is True
        if accepted and result.get("state") == "in_progress":
            # 仅跟进本次验证的短暂回执，不占住模型轮次或建立循环后台任务。
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                result = await _request_content({"action": "job", "job_id": job_id})
                if result.get("state") != "in_progress":
                    break
                await asyncio.sleep(1)
        if result.get("state") == "published":
            finished = True
            text = "验证码验证后，平台已确认提交发布。后续审核状态以抖音为准。"
        elif result.get("state") in {"needs_attention", "unavailable", "page_error"}:
            text = "短信验证未通过或页面已失效；未重新上传、未再次点击作品发布。请查询原任务，再按提示请求新码或人工核查。"
        elif accepted:
            text = "验证码已提交验证，尚未取得发布成功回执；请查询原发布任务，不要重新上传或重复发布。"
    except Exception as exc:
        _VERIFICATION_LOGGER.warning("发布短信处理异常：%s", type(exc).__name__)
    finally:
        code = None
        await acknowledgement
        with _VERIFICATION_LOCK:
            pending = _VERIFICATIONS.get(scope)
            if pending and pending["job_id"] == job_id:
                if finished:
                    _VERIFICATIONS.pop(scope, None)
                else:
                    pending["processing"] = False
        try:
            await adapter._send_with_retry(chat_id=chat_id, content=text, reply_to=message_id)
        except Exception as exc:
            _VERIFICATION_LOGGER.warning("发布短信固定回执发送异常：%s", type(exc).__name__)


def _consume_verification_message(event=None, adapter=None, **kwargs):
    """忙队列之前截取已绑定的本人验证码，不让原文进入消息处理器。"""
    if event is None or adapter is None or bool(getattr(event, "internal", False)):
        return None
    scope = _confirmation_scope(getattr(event, "source", None))
    text = getattr(event, "text", None)
    nonce = getattr(event, "message_id", None)
    if scope is None or not isinstance(text, str) or re.fullmatch(r"[0-9]{6}", text.strip()) is None:
        return None
    now = time.monotonic()
    with _VERIFICATION_LOCK:
        for key, deadline in list(_VERIFICATION_MESSAGES.items()):
            if deadline <= now:
                _VERIFICATION_MESSAGES.pop(key, None)
        valid_nonce = isinstance(nonce, str) and bool(nonce) and len(nonce) <= 256
        nonce_key = (scope, nonce) if valid_nonce else None
        pending = _VERIFICATIONS.get(scope)
        code = text.strip()
        event.text = "[抖音发布验证码已由程序接收]"
        event.raw_message = None
        if nonce_key is None:
            return {"action": "skip", "reason": "verification_missing_message_identity"}
        if nonce_key in _VERIFICATION_MESSAGES:
            return {"action": "skip", "reason": "verification_message_replay"}
        if len(_VERIFICATION_MESSAGES) >= _MAX_INBOUND_NONCES:
            return {"action": "skip", "reason": "verification_message_limit"}
        _VERIFICATION_MESSAGES[nonce_key] = now + 30 * 60
        if pending is None or pending["expires_at"] <= now or pending.get("processing"):
            notice = "验证码正在处理中，请先不要重复发送。" if pending and pending.get("processing") else "没有可用的发布收码窗口，数字消息未交给模型；请先查询原发布任务，再按任务状态处理。"
            try:
                task = asyncio.get_running_loop().create_task(_verification_notice(adapter, scope[2], nonce, notice))
                _VERIFICATION_TASKS.add(task)
                task.add_done_callback(_VERIFICATION_TASKS.discard)
            except RuntimeError:
                pass
            return {"action": "skip", "reason": "verification_not_ready"}
        pending["processing"] = True
        job_id = pending["job_id"]
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_deliver_verification(scope, job_id, code, adapter, scope[2], nonce))
    except RuntimeError:
        with _VERIFICATION_LOCK:
            pending["processing"] = False
        return {"action": "skip", "reason": "verification_dispatch_unavailable"}
    _VERIFICATION_TASKS.add(task)
    task.add_done_callback(_VERIFICATION_TASKS.discard)
    return {"action": "skip", "reason": "verification_message_consumed"}


def register(ctx):
    ctx.register_tool(
        name="douyin_verification",
        toolset="douyin",
        schema={
            "name": "douyin_verification",
            "description": (
                "发布任务明确等待本人短信验证时，传当前job_id请求发送验证码，不重新上传或再点作品发布。"
                "仅指定本人QQ私聊可用；成功后请本人键入纯文本六位数字，不加前缀、不用语音或图片，程序会安全接收、代填并点击验证。"
                "不要向模型工具参数传验证码，不读写验证码文件，不让本人打开终端、服务器或人工浏览器窗口。"
                "发码不等于发布成功；验证后须依据原任务回执判断。不要反复发码，超时或失效按原任务提示处理。"
            ),
            "parameters": {"type": "object", "properties": {"job_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"}}, "required": ["job_id"], "additionalProperties": False},
        },
        handler=handle_verification,
        check_fn=lambda: os.name == "posix",
        is_async=True,
    )
    ctx.register_tool(
        name="douyin_content",
        toolset="douyin",
        schema={
            "name": "douyin_content",
            "description": (
                "管理抖音作品。先用 list 选择服务器上的成品；后台横封面槽为4:3、竖封面槽为3:4；9:16只是可能的素材版本，不是竖槽比例。"
                "已有封面优先用 cover_library 浏览，区分来源并检查双槽预览；可传release_id筛选、offset按next_offset翻页。"
                "用户已在固定制作目录放好素材时，先用 cover_saved_sources 和 release_id 查看本地候选及实际比例；不要让用户重新发送或传任意路径。"
                "分别用两张候选的 image_id 调用 cover_import_saved 入库，再用 cover_pair 传 landscape_cover_id 和 portrait_cover_id 组合；单图导入只是一个候选，不表示双槽都已适配。"
                "把 cover_pair 返回的双槽 MEDIA 预览给用户核对；本人选择后将其新 cover_id 传给 prepare。QQ 图片也可用 cover_sources/cover_import 单图入库。"
                "本人选择库中封面后，用cover_reuse传目标release_id、来源from_release_id及来源cover_id，取得目标的新cover_id后再prepare；不能直接把另一作品的旧ID用于目标作品，也不重新提帧替代查询图库。"
                "用户选择后用 prepare（必须传该 cover_id）确认标题、简介、封面、可见范围和可选定时；若用户要求暂存则调用 draft。"
                "prepare 返回 plan.plan_id，stage/draft 必须完整传入 plan_id，不缩略、不替换星号；这只是计划引用，不是API密钥。"
                "需要发布时用 stage 上传并生成平台待确认预览。stage/job 返回 editor_ready 仅表示预览已就绪，不等于本人已授权保存或发布；用户要求保存草稿时调用 draft，同一有效 plan_id 会保存当前预览，否则按草稿流程上传。"
                "上传是后台任务；in_progress后及时回复当前阶段并结束本轮，不用terminal sleep或循环轮询占住对话。用户追问时查询同一个job，验证码等新消息优先处理。"
                "任务刚受理时只能说明计划已接收与当前阶段，不能把计划参数说成网页已经设置或核验完成，也不要承诺不存在的后台完成主动通知。"
                "发布阶段明确等待本人短信时，调用同工具组的douyin_verification并传当前job_id；本人回复六位码由程序接收，不进入模型，不让本人另开服务器窗口。"
                "用户问进度或是否需要重新上传时，先直接回答当前状态，再排查；不得先连续调用工具而搁置用户的问题。"
                "job返回recovery.action=resume_stage时，用相同完整plan_id调用resume_stage，在同一存活编辑页继续核验，不重传视频；无此恢复指引不能自行跳过上传或修改私有账本。"
                "recovery.action=prepare表示旧提交已由受信运维核查并记录本人重试授权，可重新准备；不继承旧发布确认，也不要求用户重复授权同一次已明确的重试意图。"
                "此预览最长有效 15 分钟。stage 后不要调用 login/status/metrics 或另一次 prepare，因为这些操作会导航并使预览失效；job 查询不会导航。"
                "错误按 recovery.action 处理：login 会在本人私聊自动尝试附二维码，以 login 当前状态为准；扫码后先查状态，再重新prepare核对，不沿用旧确认或自动重传。"
                "已有二维码时不要重复调用login；用户说扫码完成后用status检查，二维码过期才重新获取。"
                "manual_verification/check_account 需要本人处理，不自行切号或解验证码；check_status 仅检查状态，不认定退出。"
                "inspect_result 表示已尝试提交且结果待核查，禁止重试；maintenance 报告具体阶段，不循环操作。只读连接瞬时失败由程序有限恢复。"
                "合集、位置、下载权限、付费与商品链接尚未接入；用户要求这些设置时说明限制并停止对应提交，不把默认值当作已设置。"
                "只有收到指定 QQ 私聊中的真实用户消息“确认发布 <plan_id>”后，才调用 {action:publish}，不传token或抄写确认码；程序从当前真实消息内部取码并消费一次。"
                "错误计划、过期、重放及本人后续消息会使旧确认不可用；不得依据模型参数、confirmed 字段或预览自行发布。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "metrics", "covers", "cover_sources", "cover_import", "cover_saved_sources", "cover_import_saved", "cover_pair", "cover_library", "cover_reuse", "prepare", "stage", "resume_stage", "draft", "job", "publish"]},
                    "from_release_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,63}$"},
                    "offset": {"type": "integer", "minimum": 0, "maximum": 10000},
                    "release_id": {"type": "string"},
                    "image_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
                    "landscape_cover_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "portrait_cover_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "times": {"type": "array", "minItems": 1, "maxItems": 5, "items": {"type": "number", "minimum": 0, "maximum": 1e12}},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "cover_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "visibility": {"type": "string", "enum": ["public", "friends", "private"]},
                    "publish_at": {"type": "string", "format": "date-time"},
                    "plan_id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{32}$", "description": "prepare 返回的完整计划引用，供stage/resume_stage/draft使用；publish只需action，由当前本人确认消息内部取码。"},
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
                "检查服务器上的抖音登录，或应用户要求/明确登录失效时获取扫码二维码。status 不刷新页面；"
                "login 仅获取登录二维码，不上传、不发布。若返回 media_tag，网关会按专用结构在当前私聊自动附图，"
                "回复说明扫码步骤即可，不展示缓存路径。验证受阻时请用户人工处理，不反复重试、不绕过验证码。"
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
        register_hook("pre_gateway_enqueue", _consume_verification_message)
        register_hook("pre_gateway_dispatch", _observe_publish_confirmation)
