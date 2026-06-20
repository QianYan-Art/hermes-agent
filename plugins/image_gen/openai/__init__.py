"""OpenAI image generation backend.

Exposes an OpenAI-compatible Images API as an :class:`ImageGenProvider`
implementation. The default API model is ``gpt-image-2``. Hermes also exposes
three virtual model IDs for quality control so the ``hermes tools`` model
picker and the ``image_gen.model`` config key behave like any other
multi-model backend:

    gpt-image-2-low     ~15s   fastest, good for iteration
    gpt-image-2-medium  ~40s   default — balanced
    gpt-image-2-high    ~2min  slowest, highest fidelity

Those three IDs hit the configured API model with a different ``quality``
parameter. Output is base64 JSON → saved under the shared Hermes image cache
directory. A non-tier ``model`` value is treated as the actual API model sent
to the compatible endpoint.

Selection precedence (first hit wins):

1. Runtime ``api_model`` / non-tier ``model`` tool argument
2. ``OPENAI_IMAGE_API_MODEL`` env var
3. ``image_gen.openai.api_model`` / ``image_gen.api_model`` in ``config.yaml``
4. Non-tier ``OPENAI_IMAGE_MODEL`` / ``image_gen.openai.model`` /
   ``image_gen.model`` value
5. :data:`DEFAULT_API_MODEL` — ``gpt-image-2``

Quality-tier precedence (first hit wins):

1. ``quality`` tool argument
2. Tier ``model`` tool argument or ``OPENAI_IMAGE_MODEL`` env var
3. Tier ``image_gen.openai.model`` / ``image_gen.model`` in ``config.yaml``
4. :data:`DEFAULT_MODEL` — ``gpt-image-2-medium``

OpenAI-compatible image gateways can be configured with
``image_gen.openai.base_url`` / ``OPENAI_IMAGE_BASE_URL`` and an image-specific
``OPENAI_IMAGE_API_KEY``. ``OPENAI_API_KEY`` remains the fallback for the
official OpenAI API.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    save_url_image,
    success_response,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------
#
# All three IDs resolve to the configured underlying API model with a
# different ``quality`` setting. ``api_model`` is what gets sent to OpenAI;
# ``quality`` is the knob that changes generation time and output fidelity.

DEFAULT_API_MODEL = "gpt-image-2"
API_MODEL = DEFAULT_API_MODEL

_MODELS: Dict[str, Dict[str, Any]] = {
    "gpt-image-2-low": {
        "display": "GPT Image 2 (Low)",
        "speed": "~15s",
        "strengths": "Fast iteration, lowest cost",
        "quality": "low",
    },
    "gpt-image-2-medium": {
        "display": "GPT Image 2 (Medium)",
        "speed": "~40s",
        "strengths": "Balanced — default",
        "quality": "medium",
    },
    "gpt-image-2-high": {
        "display": "GPT Image 2 (High)",
        "speed": "~2min",
        "strengths": "Highest fidelity, strongest prompt adherence",
        "quality": "high",
    },
}

DEFAULT_MODEL = "gpt-image-2-medium"

_SIZES = {
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}

_QUALITY_TO_TIER = {
    "low": "gpt-image-2-low",
    "medium": "gpt-image-2-medium",
    "high": "gpt-image-2-high",
}

_OPTION_ENUMS = {
    "output_format": {"png", "jpeg", "webp"},
    "background": {"transparent", "opaque", "auto"},
    "moderation": {"low", "auto"},
}

_DATA_URL_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _clean_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _load_openai_config() -> Dict[str, Any]:
    """Read ``image_gen`` from config.yaml (returns {} on any failure)."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen config: %s", exc)
        return {}


def _openai_section() -> Dict[str, Any]:
    cfg = _load_openai_config()
    section = cfg.get("openai") if isinstance(cfg.get("openai"), dict) else {}
    return section if isinstance(section, dict) else {}


def _configured_model_value(cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    env_override = _clean_str(os.environ.get("OPENAI_IMAGE_MODEL"))
    if env_override:
        return env_override

    cfg = cfg if isinstance(cfg, dict) else _load_openai_config()
    openai_cfg = cfg.get("openai") if isinstance(cfg.get("openai"), dict) else {}
    if isinstance(openai_cfg, dict):
        value = _clean_str(openai_cfg.get("model"))
        if value:
            return value
    return _clean_str(cfg.get("model"))


def _resolve_model() -> Tuple[str, Dict[str, Any]]:
    """Decide which tier to use and return ``(model_id, meta)``."""
    cfg = _load_openai_config()
    selected_model = _configured_model_value(cfg)
    if selected_model in _MODELS:
        return selected_model, _MODELS[selected_model]

    return DEFAULT_MODEL, _MODELS[DEFAULT_MODEL]


def _resolve_api_model(kwargs: Dict[str, Any]) -> str:
    """Resolve the actual Images API ``model`` value to send."""
    explicit_model = (
        _clean_str(kwargs.get("api_model"))
        or _clean_str(kwargs.get("image_model"))
    )
    if explicit_model:
        return explicit_model

    requested_model = _clean_str(kwargs.get("model"))
    if requested_model and requested_model not in _MODELS:
        return requested_model

    env_api_model = _clean_str(os.environ.get("OPENAI_IMAGE_API_MODEL"))
    if env_api_model:
        return env_api_model

    cfg = _load_openai_config()
    openai_cfg = cfg.get("openai") if isinstance(cfg.get("openai"), dict) else {}
    if isinstance(openai_cfg, dict):
        config_api_model = _clean_str(openai_cfg.get("api_model"))
        if config_api_model:
            return config_api_model

    top_api_model = _clean_str(cfg.get("api_model"))
    if top_api_model:
        return top_api_model

    configured_model = _configured_model_value(cfg)
    if configured_model and configured_model not in _MODELS:
        return configured_model

    return DEFAULT_API_MODEL


def _resolve_tier(kwargs: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Optional[str]]:
    """Resolve the requested virtual model tier and validate quality override."""
    tier_id, meta = _resolve_model()
    requested_model = _clean_str(kwargs.get("model"))
    if requested_model in _MODELS:
        tier_id = requested_model
        meta = _MODELS[tier_id]

    requested_quality = _clean_str(kwargs.get("quality"))
    if requested_quality:
        quality = requested_quality.lower()
        if quality not in _QUALITY_TO_TIER:
            return tier_id, meta, "quality must be one of: low, medium, high"
        tier_id = _QUALITY_TO_TIER[quality]
        meta = _MODELS[tier_id]

    return tier_id, meta, None


def _int_option(
    kwargs: Dict[str, Any],
    key: str,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> Tuple[Optional[int], Optional[str]]:
    value = kwargs.get(key)
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"{key} must be an integer"
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{key} must be an integer"
    if minimum is not None and parsed < minimum:
        return None, f"{key} must be >= {minimum}"
    if maximum is not None and parsed > maximum:
        return None, f"{key} must be <= {maximum}"
    return parsed, None


def _enum_option(
    kwargs: Dict[str, Any],
    key: str,
) -> Tuple[Optional[str], Optional[str]]:
    value = _clean_str(kwargs.get(key))
    if value is None:
        return None, None
    normalized = value.lower()
    allowed = _OPTION_ENUMS[key]
    if normalized not in allowed:
        return None, f"{key} must be one of: {', '.join(sorted(allowed))}"
    return normalized, None


def _resolve_client_options() -> Dict[str, Any]:
    """Resolve OpenAI SDK options for official or compatible image endpoints."""
    openai_cfg = _openai_section()

    api_key = (
        _clean_str(os.getenv("OPENAI_IMAGE_API_KEY"))
        or _clean_str(openai_cfg.get("api_key"))
        or _clean_str(os.getenv("OPENAI_API_KEY"))
    )
    base_url = (
        _clean_str(os.getenv("OPENAI_IMAGE_BASE_URL"))
        or _clean_str(openai_cfg.get("base_url"))
    )

    timeout: Optional[float] = None
    raw_timeout = os.getenv("OPENAI_IMAGE_TIMEOUT")
    if raw_timeout is None:
        raw_timeout = openai_cfg.get("timeout")
    if raw_timeout is not None:
        try:
            parsed = float(raw_timeout)
            if parsed > 0:
                timeout = parsed
        except (TypeError, ValueError):
            logger.debug("Ignoring invalid OPENAI image timeout: %r", raw_timeout)

    options: Dict[str, Any] = {}
    if api_key:
        options["api_key"] = api_key
    if base_url:
        options["base_url"] = base_url
    if timeout is not None:
        options["timeout"] = timeout
    return options


def _save_data_url_image(data_url: str, *, prefix: str) -> str:
    header, sep, payload = data_url.partition(",")
    if sep != "," or not header.lower().startswith("data:"):
        raise ValueError("invalid data URL image")
    media_type = header[5:].split(";", 1)[0].strip().lower()
    extension = _DATA_URL_EXTENSIONS.get(media_type, "png")
    return str(save_b64_image(payload, prefix=prefix, extension=extension))


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class OpenAIImageGenProvider(ImageGenProvider):
    """OpenAI ``images.generate`` backend — gpt-image-2 at low/medium/high."""

    @property
    def name(self) -> str:
        return "openai"

    @property
    def display_name(self) -> str:
        return "OpenAI"

    def is_available(self) -> bool:
        if not _resolve_client_options().get("api_key"):
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": model_id,
                "display": meta["display"],
                "speed": meta["speed"],
                "strengths": meta["strengths"],
                "price": "varies",
            }
            for model_id, meta in _MODELS.items()
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "OpenAI",
            "badge": "paid",
            "tag": "OpenAI-compatible Images API with configurable model and quality tiers",
            "env_vars": [
                {
                    "key": "OPENAI_IMAGE_API_KEY",
                    "prompt": "OpenAI-compatible image API key",
                    "url": "https://platform.openai.com/api-keys",
                },
                {
                    "key": "OPENAI_IMAGE_BASE_URL",
                    "prompt": "Optional OpenAI-compatible image base URL",
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
                provider="openai",
                aspect_ratio=aspect,
            )

        client_options = _resolve_client_options()
        if not client_options.get("api_key"):
            return error_response(
                error=(
                    "OPENAI_IMAGE_API_KEY or OPENAI_API_KEY not set. Run "
                    "`hermes tools` → Image Generation → OpenAI to configure, "
                    "or set the key in the runtime environment."
                ),
                error_type="auth_required",
                provider="openai",
                aspect_ratio=aspect,
            )

        try:
            import openai
        except ImportError:
            return error_response(
                error="openai Python package not installed (pip install openai)",
                error_type="missing_dependency",
                provider="openai",
                aspect_ratio=aspect,
            )

        tier_id, meta, option_error = _resolve_tier(kwargs)
        if option_error:
            return error_response(
                error=option_error,
                error_type="invalid_argument",
                provider="openai",
                aspect_ratio=aspect,
            )

        api_model = _resolve_api_model(kwargs)
        result_model = tier_id if api_model == DEFAULT_API_MODEL else api_model
        size = _SIZES.get(aspect, _SIZES["square"])

        requested_count = kwargs.get("num_images")
        if requested_count is None:
            requested_count = kwargs.get("n")
        count, option_error = _int_option(
            {"num_images": requested_count}, "num_images", minimum=1, maximum=10,
        )
        if option_error:
            return error_response(
                error=option_error,
                error_type="invalid_argument",
                provider="openai",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        payload: Dict[str, Any] = {
            "model": api_model,
            "prompt": prompt,
            "size": size,
            "n": count or 1,
            "quality": meta["quality"],
        }

        for key in ("output_format", "background", "moderation"):
            value, option_error = _enum_option(kwargs, key)
            if option_error:
                return error_response(
                    error=option_error,
                    error_type="invalid_argument",
                    provider="openai",
                    model=tier_id,
                    prompt=prompt,
                    aspect_ratio=aspect,
                )
            if value is not None:
                payload[key] = value

        compression, option_error = _int_option(
            kwargs, "output_compression", minimum=0, maximum=100,
        )
        if option_error:
            return error_response(
                error=option_error,
                error_type="invalid_argument",
                provider="openai",
                model=tier_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        if compression is not None:
            if payload.get("output_format") not in {"jpeg", "webp"}:
                return error_response(
                    error="output_compression requires output_format jpeg or webp",
                    error_type="invalid_argument",
                    provider="openai",
                    model=tier_id,
                    prompt=prompt,
                    aspect_ratio=aspect,
                )
            payload["output_compression"] = compression

        try:
            client = openai.OpenAI(**client_options)
            response = client.images.generate(**payload)
        except Exception as exc:
            logger.debug("OpenAI image generation failed", exc_info=True)
            return error_response(
                error=f"OpenAI image generation failed: {exc}",
                error_type="api_error",
                provider="openai",
                model=result_model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        data = getattr(response, "data", None) or []
        if not data:
            return error_response(
                error="OpenAI returned no image data",
                error_type="empty_response",
                provider="openai",
                model=result_model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        image_refs: List[str] = []
        revised_prompts: List[str] = []

        for item in data:
            b64 = getattr(item, "b64_json", None)
            url = getattr(item, "url", None)
            revised_prompt = getattr(item, "revised_prompt", None)
            if revised_prompt:
                revised_prompts.append(revised_prompt)

            if b64:
                try:
                    saved_path = save_b64_image(b64, prefix=f"openai_{tier_id}")
                except Exception as exc:
                    return error_response(
                        error=f"Could not save image to cache: {exc}",
                        error_type="io_error",
                        provider="openai",
                        model=result_model,
                        prompt=prompt,
                        aspect_ratio=aspect,
                    )
                image_refs.append(str(saved_path))
            elif url:
                # Defensive: cache URL/data-URL output locally so the gateway
                # always receives a stable path when possible.
                try:
                    if str(url).startswith("data:"):
                        image_refs.append(
                            _save_data_url_image(str(url), prefix=f"openai_{tier_id}")
                        )
                    else:
                        saved_path = save_url_image(url, prefix=f"openai_{tier_id}")
                        image_refs.append(str(saved_path))
                except Exception as exc:
                    logger.warning(
                        "OpenAI image URL %s could not be cached (%s); falling back to bare URL.",
                        url,
                        exc,
                    )
                    image_refs.append(str(url))

        if not image_refs:
            return error_response(
                error="OpenAI response contained neither b64_json nor URL",
                error_type="empty_response",
                provider="openai",
                model=result_model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        extra: Dict[str, Any] = {
            "api_model": api_model,
            "quality_tier": tier_id,
            "size": size,
            "quality": meta["quality"],
            "num_images": len(image_refs),
        }
        if len(image_refs) > 1:
            extra["images"] = image_refs
        if revised_prompts:
            extra["revised_prompt"] = revised_prompts[0]
            if len(revised_prompts) > 1:
                extra["revised_prompts"] = revised_prompts
        for key in (
            "output_format",
            "background",
            "moderation",
            "output_compression",
        ):
            if key in payload:
                extra[key] = payload[key]

        return success_response(
            image=image_refs[0],
            model=result_model,
            prompt=prompt,
            aspect_ratio=aspect,
            provider="openai",
            extra=extra,
        )


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------


def register(ctx) -> None:
    """Plugin entry point — wire ``OpenAIImageGenProvider`` into the registry."""
    ctx.register_image_gen_provider(OpenAIImageGenProvider())
