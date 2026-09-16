"""Kimi Code 官方端点的真实客户端标识与缓存任务键。"""

import hashlib
from urllib.parse import urlsplit
from uuid import uuid4

from hermes_cli import __version__


def is_kimi_code_endpoint(base_url: str | None) -> bool:
    if not base_url:
        return False
    try:
        parsed = urlsplit(str(base_url).strip())
        return (
            parsed.scheme == "https"
            and parsed.hostname == "api.kimi.com"
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
            and parsed.path.rstrip("/") in {"/coding", "/coding/v1"}
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def build_kimi_request_options(session_id: str | None = None) -> dict:
    """已有会话生成稳定键；无会话的独立调用使用一次性任务键。"""
    identity = str(session_id or "").strip()
    if not identity:
        identity = uuid4().hex
    key = "hermes-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return {
        "extra_headers": {"User-Agent": f"Tangyuge-Hermes/{__version__}"},
        "prompt_cache_key": key,
    }
