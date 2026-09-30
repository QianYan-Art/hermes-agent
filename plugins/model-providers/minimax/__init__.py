"""MiniMax 国际 API 与 OAuth provider profiles。

它们的 inference_base_url 均以 /anthropic 结尾，因此使用
anthropic_messages API 模式。
"""

from providers import register_provider
from providers.base import ProviderProfile

minimax = ProviderProfile(
    name="minimax",
    aliases=("mini-max",),
    api_mode="anthropic_messages",
    env_vars=("MINIMAX_API_KEY",),
    base_url="https://api.minimax.io/anthropic",
    auth_type="api_key",
    default_aux_model="MiniMax-M3",
)

minimax_oauth = ProviderProfile(
    name="minimax-oauth",
    aliases=("minimax_oauth", "minimax-oauth-io"),
    api_mode="anthropic_messages",
    display_name="MiniMax (OAuth)",
    description="MiniMax via OAuth browser flow — no API key required",
    signup_url="https://api.minimax.io/",
    env_vars=(),  # OAuth — tokens in auth.json, not env
    base_url="https://api.minimax.io/anthropic",
    auth_type="oauth_external",
    default_aux_model="MiniMax-M2.7",
)

register_provider(minimax)
register_provider(minimax_oauth)
