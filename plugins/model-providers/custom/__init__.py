"""Custom / Ollama (local) provider profile.

Covers any endpoint registered as provider="custom", including local
Ollama instances. Key quirks:
  - ollama_num_ctx → extra_body.options.num_ctx (local context window)
  - reasoning_config disabled → extra_body.think = False
"""

from typing import Any

from agent.kimi_code import build_kimi_request_options, is_kimi_code_endpoint

from providers import register_provider
from providers.base import ProviderProfile


def _is_kimi_code_base_url(base_url: str | None) -> bool:
    """仅识别 Kimi Code 官方主机及其精确 coding 路径。"""
    return is_kimi_code_endpoint(base_url)


class CustomProfile(ProviderProfile):
    """Custom/Ollama local provider — think=false and num_ctx support."""

    def build_api_kwargs_extras(
        self,
        *,
        reasoning_config: dict | None = None,
        ollama_num_ctx: int | None = None,
        **ctx: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        extra_body: dict[str, Any] = {}

        if _is_kimi_code_base_url(ctx.get("base_url")):
            options = build_kimi_request_options(ctx.get("session_id"))
            config = reasoning_config if isinstance(reasoning_config, dict) else {}
            effort = str(config.get("effort") or "").strip().lower()
            if config.get("enabled", True) is False or effort == "none":
                return {"thinking": {"type": "disabled"}}, options

            kimi_effort = {
                "minimal": "low",
                "low": "low",
                "medium": "high",
                "high": "high",
                "xhigh": "max",
                "max": "max",
            }.get(effort, "max")
            return (
                {"thinking": {"type": "enabled"}},
                {**options, "reasoning_effort": kimi_effort},
            )

        # Ollama context window
        if ollama_num_ctx:
            options = extra_body.get("options", {})
            options["num_ctx"] = ollama_num_ctx
            extra_body["options"] = options

        # Disable thinking when reasoning is turned off
        if reasoning_config and isinstance(reasoning_config, dict):
            _effort = (reasoning_config.get("effort") or "").strip().lower()
            _enabled = reasoning_config.get("enabled", True)
            if _effort == "none" or _enabled is False:
                extra_body["think"] = False

        return extra_body, {}

    def fetch_models(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 8.0,
    ) -> list[str] | None:
        """Custom/Ollama: base_url is user-configured; fetch if set."""
        if not self.base_url:
            return None
        return super().fetch_models(api_key=api_key, timeout=timeout)


custom = CustomProfile(
    name="custom",
    aliases=(
        "ollama",
        "local",
        "vllm",
        "llamacpp",
        "llama.cpp",
        "llama-cpp",
    ),
    env_vars=(),  # No fixed key — custom endpoint
    base_url="",  # User-configured
)

register_provider(custom)
