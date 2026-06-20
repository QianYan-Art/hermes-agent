"""HYBGZS image generation backend.

The endpoint is OpenAI-compatible for ``/v1/chat/completions`` but does not
implement ``/v1/images/generations``. Image models return markdown containing a
``data:image/...;base64,...`` URI, which this backend extracts and saves under
the shared Hermes image cache directory.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ai.hybgzs.com/v1"
DEFAULT_MODEL = "gemini-3.1-flash-image"

_MODELS: Dict[str, Dict[str, str]] = {
    "gemini-3.1-flash-image": {
        "display": "Gemini 3.1 Flash Image",
        "speed": "medium",
        "strengths": "General image generation",
    },
    "hyb-Optimal/antigravity/gemini-3-pro-image": {
        "display": "Gemini 3 Pro Image",
        "speed": "slower",
        "strengths": "Higher-detail image generation",
    },
}

_ASPECT_HINTS = {
    "landscape": "landscape 16:9",
    "square": "square 1:1",
    "portrait": "portrait 9:16",
}

_DATA_URI_RE = re.compile(
    r"data:image/(?P<fmt>png|jpe?g|webp);base64,(?P<b64>[A-Za-z0-9+/=\r\n]+)",
    re.IGNORECASE,
)


def _load_image_gen_config() -> Dict[str, Any]:
    """Read ``image_gen`` from config.yaml."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen config: %s", exc)
        return {}


def _resolve_config() -> Tuple[str, str, int]:
    cfg = _load_image_gen_config()
    hybgzs_cfg = cfg.get("hybgzs") if isinstance(cfg.get("hybgzs"), dict) else {}
    base_url = str(
        hybgzs_cfg.get("base_url")
        or os.getenv("HYBGZS_IMAGE_BASE_URL")
        or DEFAULT_BASE_URL
    ).strip().rstrip("/")
    model = str(
        hybgzs_cfg.get("model")
        or cfg.get("model")
        or os.getenv("HYBGZS_IMAGE_MODEL")
        or DEFAULT_MODEL
    ).strip()
    timeout = int(hybgzs_cfg.get("timeout") or os.getenv("HYBGZS_IMAGE_TIMEOUT") or 180)
    return base_url, model, timeout


def _extract_message_text(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def _extract_data_uri_image(content: str) -> Tuple[Optional[str], Optional[str]]:
    match = _DATA_URI_RE.search(content or "")
    if not match:
        return None, None
    fmt = match.group("fmt").lower()
    extension = "jpg" if fmt in ("jpg", "jpeg") else fmt
    return match.group("b64").replace("\n", "").replace("\r", ""), extension


class HYBGZSImageGenProvider(ImageGenProvider):
    @property
    def name(self) -> str:
        return "hybgzs"

    @property
    def display_name(self) -> str:
        return "HYBGZS"

    def is_available(self) -> bool:
        return bool(os.getenv("HYBGZS_IMAGE_API_KEY", "").strip())

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": model_id,
                "display": meta["display"],
                "speed": meta["speed"],
                "strengths": meta["strengths"],
                "price": "provider-defined",
            }
            for model_id, meta in _MODELS.items()
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "HYBGZS",
            "badge": "custom",
            "tag": "OpenAI-compatible chat image endpoint",
            "env_vars": [
                {
                    "key": "HYBGZS_IMAGE_API_KEY",
                    "prompt": "HYBGZS image API key",
                    "url": DEFAULT_BASE_URL,
                },
            ],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)
        if not prompt:
            return error_response(
                error="Prompt is required and must be a non-empty string",
                error_type="invalid_argument",
                provider=self.name,
                aspect_ratio=aspect,
            )

        api_key = os.getenv("HYBGZS_IMAGE_API_KEY", "").strip()
        if not api_key:
            return error_response(
                error="HYBGZS_IMAGE_API_KEY not set",
                error_type="auth_required",
                provider=self.name,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        base_url, model, timeout = _resolve_config()
        render_prompt = (
            f"{prompt}\n\n"
            f"Image requirements: {_ASPECT_HINTS.get(aspect, _ASPECT_HINTS['landscape'])}. "
            "Return the generated image."
        )
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": render_prompt}],
        }

        try:
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            return error_response(
                error=f"HYBGZS image API error (HTTP {exc.response.status_code}): {detail}",
                error_type="provider_http_error",
                provider=self.name,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except Exception as exc:
            return error_response(
                error=f"HYBGZS image request failed: {exc}",
                error_type="provider_error",
                provider=self.name,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        choices = data.get("choices") if isinstance(data, dict) else None
        message = choices[0].get("message", {}) if choices else {}
        content = _extract_message_text(message)
        b64_data, extension = _extract_data_uri_image(content)
        if not b64_data or not extension:
            return error_response(
                error="HYBGZS response contained no data-URI image",
                error_type="empty_response",
                provider=self.name,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        try:
            image_path = save_b64_image(
                b64_data,
                prefix="hybgzs",
                extension=extension,
            )
        except Exception as exc:
            return error_response(
                error=f"Could not save HYBGZS image: {exc}",
                error_type="save_failed",
                provider=self.name,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        return success_response(
            image=str(image_path),
            model=model,
            prompt=prompt,
            aspect_ratio=aspect,
            provider=self.name,
        )


def register(ctx: Any) -> None:
    ctx.register_image_gen_provider(HYBGZSImageGenProvider())
