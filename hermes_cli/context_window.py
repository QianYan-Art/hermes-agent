"""Helpers for the /context command and model context persistence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DEFAULT_CONTEXT_WINDOW = 256_000


@dataclass(frozen=True)
class ContextWindowResult:
    value: int
    source: str


def parse_context_window(value: str) -> int:
    """解析 token 数；k 为 1024，m 为 1024²，不带单位的数字保持原值。"""
    raw = (value or "").strip().lower().replace("_", "").replace(",", "")
    if not raw:
        raise ValueError("missing context window size")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([km]?)", raw)
    if not match:
        raise ValueError("use a plain integer, 256k, or 1m")
    number = float(match.group(1))
    suffix = match.group(2)
    multiplier = 1
    if suffix == "k":
        multiplier = 1024
    elif suffix == "m":
        multiplier = 1024 * 1024
    parsed = int(number * multiplier)
    if parsed <= 0:
        raise ValueError("context window must be positive")
    return parsed


def format_context_window(value: int) -> str:
    return f"{int(value):,} tokens"


def _read_config_context_length(config: dict[str, Any] | None) -> int | None:
    if not isinstance(config, dict):
        return None
    model_cfg = (config or {}).get("model", {})
    if not isinstance(model_cfg, dict):
        return None
    raw = model_cfg.get("context_length")
    if raw is None:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def read_explicit_context_length(
    config: dict[str, Any] | None, *, model: str, provider: str = "",
    base_url: str = "", custom_providers: list | None = None,
) -> int | None:
    """读取当前作用域的显式窗口，供切换失败时保留，不触发网络探测。"""
    value = _read_config_context_length(config)
    if value is not None:
        return value
    if not base_url:
        base_url = next(
            (p.get("base_url", "") for p in custom_providers or []
             if isinstance(p, dict) and p.get("name") == provider), "",
        )
    if base_url and custom_providers:
        from hermes_cli.config import get_custom_provider_context_length
        return get_custom_provider_context_length(
            model=model, base_url=base_url, custom_providers=custom_providers,
        )
    return None


def set_config_context_length(config: dict[str, Any], value: int) -> dict[str, Any]:
    """Mutate config so ``model.context_length`` is set to *value*."""
    raw_model = config.get("model")
    if isinstance(raw_model, dict):
        model_cfg = raw_model
    elif isinstance(raw_model, str) and raw_model.strip():
        model_cfg = {"default": raw_model.strip()}
        config["model"] = model_cfg
    else:
        model_cfg = {}
        config["model"] = model_cfg
    model_cfg["context_length"] = int(value)
    return config


def resolve_context_window(
    *,
    model: str,
    provider: str = "",
    base_url: str = "",
    api_key: str = "",
    model_info: Any = None,
    custom_providers: list | None = None,
    config: dict[str, Any] | None = None,
    use_config_override: bool = True,
    fallback_context_length: int | None = None,
) -> ContextWindowResult:
    """区分配置、已知模型窗口、保留值与默认回落，避免把兜底误报为探测。"""
    config_context = _read_config_context_length(config) if use_config_override else None
    if config_context:
        return ContextWindowResult(config_context, "config")
    if custom_providers and base_url:
        from hermes_cli.config import get_custom_provider_context_length
        model_context = get_custom_provider_context_length(
            model=model, base_url=base_url, custom_providers=custom_providers,
        )
        if model_context:
            return ContextWindowResult(int(model_context), "model_config")
    try:
        from hermes_cli.model_switch import resolve_display_context_length

        resolved = resolve_display_context_length(
            model,
            provider,
            base_url=base_url or "",
            api_key=api_key or "",
            model_info=model_info,
            custom_providers=custom_providers,
            config_context_length=config_context,
            allow_fallback=False,
        )
    except Exception:
        resolved = None
    if resolved:
        return ContextWindowResult(int(resolved), "detected")
    if isinstance(fallback_context_length, int) and not isinstance(fallback_context_length, bool) and fallback_context_length > 0:
        return ContextWindowResult(fallback_context_length, "retained")
    return ContextWindowResult(DEFAULT_CONTEXT_WINDOW, "fallback")
