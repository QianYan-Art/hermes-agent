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
    """Parse context-window sizes such as ``256k``, ``1m``, or ``262144``."""
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
        multiplier = 1_000
    elif suffix == "m":
        multiplier = 1_000_000
    parsed = int(number * multiplier)
    if parsed <= 0:
        raise ValueError("context window must be positive")
    return parsed


def format_context_window(value: int) -> str:
    return f"{int(value):,} tokens"


def _read_config_context_length(config: dict[str, Any] | None) -> int | None:
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
) -> ContextWindowResult:
    """Resolve a model context window, falling back to 256k."""
    config_context = _read_config_context_length(config) if use_config_override else None
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
        )
    except Exception:
        resolved = None
    if resolved:
        source = "config" if config_context and int(resolved) == config_context else "detected"
        return ContextWindowResult(int(resolved), source)
    return ContextWindowResult(DEFAULT_CONTEXT_WINDOW, "fallback")
