"""验证 Kimi Code 沿用命名自定义 provider 和环境变量密钥。"""

import pytest

from hermes_cli import runtime_provider as rp
from hermes_cli.config import (
    get_compatible_custom_providers,
    get_custom_provider_context_length,
)
from hermes_cli.context_window import resolve_context_window


@pytest.fixture
def kimi_config():
    return {
        "model": {
            "provider": "kimi-code",
            "default": "kimi-for-coding",
            "context_length": 262144,
        },
        "agent": {"reasoning_effort": "low"},
        "providers": {
            "kimi-code": {
                "name": "kimi-code",
                "base_url": "https://api.kimi.com/coding/v1",
                "key_env": "KIMI_CODE_API_KEY",
                "default_model": "kimi-for-coding",
                "transport": "chat_completions",
                "models": {"kimi-for-coding": {"context_length": 262144}},
            }
        },
    }


def test_kimi_code_resolves_env_key_and_explicit_openai_transport(monkeypatch, kimi_config):
    monkeypatch.setenv("KIMI_CODE_API_KEY", "test-kimi-code-key")
    monkeypatch.setattr(rp, "load_config", lambda: kimi_config)
    monkeypatch.setattr(rp, "load_pool", lambda *args, **kwargs: None)
    resolved = rp.resolve_runtime_provider(requested="kimi-code")
    assert resolved["provider"] == "custom"
    assert resolved["requested_provider"] == "kimi-code"
    assert resolved["api_key"] == "test-kimi-code-key"
    assert resolved["base_url"] == "https://api.kimi.com/coding/v1"
    assert resolved["api_mode"] == "chat_completions"
    assert resolved["model"] == "kimi-for-coding"
    assert "api_key" not in kimi_config["providers"]["kimi-code"]


def test_kimi_code_preserves_configured_context_limit(kimi_config):
    providers = get_compatible_custom_providers(kimi_config)
    assert get_custom_provider_context_length(
        model="kimi-for-coding",
        base_url="https://api.kimi.com/coding/v1",
        custom_providers=providers,
    ) == 262144
    result = resolve_context_window(
        model="kimi-for-coding",
        provider="custom",
        base_url="https://api.kimi.com/coding/v1",
        custom_providers=providers,
        config=kimi_config,
    )
    assert result.value == 262144


def test_bare_context_override_is_not_reinterpreted(kimi_config):
    kimi_config["model"]["context_length"] = 512000
    result = resolve_context_window(
        model="kimi-for-coding",
        provider="custom",
        base_url="https://api.kimi.com/coding/v1",
        custom_providers=get_compatible_custom_providers(kimi_config),
        config=kimi_config,
    )
    assert result.value == 512000


def test_auto_context_keeps_provider_model_limit(kimi_config):
    kimi_config["model"]["context_length"] = 524288
    result = resolve_context_window(
        model="kimi-for-coding",
        provider="custom",
        base_url="https://api.kimi.com/coding/v1",
        custom_providers=get_compatible_custom_providers(kimi_config),
        config=kimi_config,
        use_config_override=False,
    )
    assert result.value == 262144
