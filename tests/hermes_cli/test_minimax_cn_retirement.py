"""MiniMax 中国区 CLI provider 退役回归测试。"""

import pytest

from hermes_cli.auth import (
    AuthError,
    PROVIDER_REGISTRY,
    resolve_api_key_provider_credentials,
    resolve_provider,
)
from hermes_cli.config import OPTIONAL_ENV_VARS


_RETIRED_PROVIDER_IDS = ("minimax-cn", "minimax-china", "minimax_cn")


def test_retired_provider_ids_fail_closed():
    for provider_id in _RETIRED_PROVIDER_IDS:
        with pytest.raises(AuthError) as exc_info:
            resolve_provider(provider_id)
        assert exc_info.value.code == "invalid_provider"

        with pytest.raises(AuthError) as exc_info:
            resolve_api_key_provider_credentials(provider_id)
        assert exc_info.value.code == "invalid_provider"


def test_retired_cn_environment_variables_are_not_setup_prompts():
    assert "minimax-cn" not in PROVIDER_REGISTRY
    assert "MINIMAX_CN_API_KEY" not in OPTIONAL_ENV_VARS
    assert "MINIMAX_CN_BASE_URL" not in OPTIONAL_ENV_VARS


def test_supported_provider_resolution_remains_available():
    assert resolve_provider("minimax") == "minimax"
    assert resolve_provider("minimax-oauth") == "minimax-oauth"
    assert resolve_provider("deepseek") == "deepseek"
    assert resolve_provider("custom") == "custom"
