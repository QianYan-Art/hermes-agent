"""验证辅助客户端协议：Kimi Code 默认 Chat Completions，显式协议优先。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "OPENAI_API_KEY", "OPENAI_BASE_URL",
        "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN",
        "KIMI_API_KEY", "KIMI_CODING_API_KEY", "KIMI_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# URL detection helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected,label", [
    ("https://api.kimi.com/coding/v1", False, "Kimi Coding Plan /v1"),
    ("https://api.kimi.com/coding", False, "Kimi Coding Plan no /v1"),
    ("https://api.moonshot.ai/v1", False, "Moonshot legacy"),
    ("https://api.minimax.io/anthropic", True, "MiniMax /anthropic"),
    ("https://litellm.example.com/v1/anthropic", True, "/anthropic suffix"),
    ("https://api.anthropic.com", True, "native Anthropic"),
    ("https://api.anthropic.com/v1", True, "native Anthropic /v1"),
    ("https://openrouter.ai/api/v1", False, "OpenRouter"),
    ("https://api.openai.com/v1", False, "OpenAI"),
    ("https://inference-api.nousresearch.com/v1", False, "Nous"),
    ("", False, "empty"),
    (None, False, "None"),
])
def test_endpoint_speaks_anthropic_messages(url, expected, label):
    from agent.auxiliary_client import _endpoint_speaks_anthropic_messages
    assert _endpoint_speaks_anthropic_messages(url) is expected, (
        f"{label}: {url!r} should be {expected}"
    )


# ---------------------------------------------------------------------------
# _maybe_wrap_anthropic decision table
# ---------------------------------------------------------------------------

def test_maybe_wrap_anthropic_rewraps_kimi_coding_url():
    """Kimi Code 添加请求元数据，使用 Chat Completions 协议。"""
    from agent.auxiliary_client import _maybe_wrap_anthropic, _KimiAuxiliaryClient

    plain_client = MagicMock(name="plain_openai")
    fake_anthropic = MagicMock(name="anthropic_sdk_client")

    with patch(
        "agent.anthropic_adapter.build_anthropic_client",
        return_value=fake_anthropic,
    ):
        result = _maybe_wrap_anthropic(
            plain_client, "kimi-for-coding", "sk-kimi-test",
            "https://api.kimi.com/coding", api_mode=None,
        )
    assert isinstance(result, _KimiAuxiliaryClient)


def test_maybe_wrap_anthropic_rewraps_slash_anthropic_url():
    """Plain OpenAI client pointed at any /anthropic URL gets rewrapped."""
    from agent.auxiliary_client import _maybe_wrap_anthropic, AnthropicAuxiliaryClient

    plain_client = MagicMock(name="plain_openai")
    fake_anthropic = MagicMock(name="anthropic_sdk_client")

    with patch(
        "agent.anthropic_adapter.build_anthropic_client",
        return_value=fake_anthropic,
    ):
        result = _maybe_wrap_anthropic(
            plain_client, "MiniMax-M2.7", "mm-key",
            "https://api.minimax.io/anthropic", api_mode=None,
        )
    assert isinstance(result, AnthropicAuxiliaryClient)


def test_maybe_wrap_anthropic_skips_openai_wire_urls():
    """OpenRouter / OpenAI / Moonshot-legacy stay as plain OpenAI clients."""
    from agent.auxiliary_client import _maybe_wrap_anthropic, AnthropicAuxiliaryClient

    plain_client = MagicMock(name="plain_openai")
    # No patch on build_anthropic_client — if the function tried to call it,
    # we'd get an AttributeError-style failure. The point is it shouldn't.
    result = _maybe_wrap_anthropic(
        plain_client, "claude-sonnet-4.6", "sk-or-test",
        "https://openrouter.ai/api/v1", api_mode=None,
    )
    assert result is plain_client
    assert not isinstance(result, AnthropicAuxiliaryClient)


def test_maybe_wrap_anthropic_respects_explicit_chat_completions():
    """api_mode=chat_completions overrides URL heuristics."""
    from agent.auxiliary_client import _maybe_wrap_anthropic, AnthropicAuxiliaryClient, _KimiAuxiliaryClient

    plain_client = MagicMock(name="plain_openai")
    result = _maybe_wrap_anthropic(
        plain_client, "kimi-for-coding", "sk-kimi-test",
        "https://api.kimi.com/coding",
        api_mode="chat_completions",  # explicit override
    )
    assert isinstance(result, _KimiAuxiliaryClient)
    assert not isinstance(result, AnthropicAuxiliaryClient)


def test_maybe_wrap_anthropic_honors_explicit_anthropic_messages():
    """api_mode=anthropic_messages wraps even when URL wouldn't trigger."""
    from agent.auxiliary_client import _maybe_wrap_anthropic, AnthropicAuxiliaryClient

    plain_client = MagicMock(name="plain_openai")
    fake_anthropic = MagicMock(name="anthropic_sdk_client")

    with patch(
        "agent.anthropic_adapter.build_anthropic_client",
        return_value=fake_anthropic,
    ):
        result = _maybe_wrap_anthropic(
            plain_client, "model-name", "some-key",
            "https://opaque.internal/v1",  # URL alone wouldn't trigger
            api_mode="anthropic_messages",
        )
    assert isinstance(result, AnthropicAuxiliaryClient)


def test_maybe_wrap_anthropic_double_wrap_safe():
    """Already-wrapped AnthropicAuxiliaryClient passes through unchanged."""
    from agent.auxiliary_client import _maybe_wrap_anthropic, AnthropicAuxiliaryClient

    already_wrapped = MagicMock(spec=AnthropicAuxiliaryClient)
    result = _maybe_wrap_anthropic(
        already_wrapped, "model", "key",
        "https://api.kimi.com/coding", api_mode=None,
    )
    assert result is already_wrapped


def test_maybe_wrap_anthropic_codex_client_passes_through():
    """CodexAuxiliaryClient is never re-dispatched."""
    from agent.auxiliary_client import (
        _maybe_wrap_anthropic,
        CodexAuxiliaryClient,
        AnthropicAuxiliaryClient,
    )

    codex_client = MagicMock(spec=CodexAuxiliaryClient)
    result = _maybe_wrap_anthropic(
        codex_client, "model", "key",
        "https://api.kimi.com/coding", api_mode=None,
    )
    assert result is codex_client
    assert not isinstance(result, AnthropicAuxiliaryClient)


def test_maybe_wrap_anthropic_sdk_missing_falls_back():
    """ImportError on anthropic SDK returns plain client with warning."""
    from agent.auxiliary_client import _maybe_wrap_anthropic, AnthropicAuxiliaryClient

    plain_client = MagicMock(name="plain_openai")

    def _raise_import(*args, **kwargs):
        raise ImportError("no anthropic SDK")

    with patch(
        "agent.anthropic_adapter.build_anthropic_client",
        side_effect=_raise_import,
    ):
        # The ImportError is caught on the `from ... import` line inside
        # _maybe_wrap_anthropic, which runs before build_anthropic_client is
        # called. To exercise the ImportError path we need to patch the
        # module lookup itself.
        import sys as _sys
        saved = _sys.modules.get("agent.anthropic_adapter")
        _sys.modules["agent.anthropic_adapter"] = None  # force ImportError
        try:
            result = _maybe_wrap_anthropic(
                plain_client, "kimi-for-coding", "sk-kimi-test",
                "https://api.anthropic.com", api_mode=None,
            )
        finally:
            if saved is not None:
                _sys.modules["agent.anthropic_adapter"] = saved
            else:
                _sys.modules.pop("agent.anthropic_adapter", None)

    assert result is plain_client
    assert not isinstance(result, AnthropicAuxiliaryClient)


# ---------------------------------------------------------------------------
# Integration: resolve_provider_client for named kimi-coding provider
# ---------------------------------------------------------------------------

def test_resolve_named_kimi_client_uses_chat_completions(monkeypatch, tmp_path):
    """命名自定义 Kimi 配置沿当前请求协议解析，不依赖内置 provider。"""
    import yaml
    from agent.auxiliary_client import (
        resolve_provider_client,
        _KimiAuxiliaryClient,
    )

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({
        "model": {"default": "kimi-for-coding", "provider": "custom:kimi"},
        "custom_providers": [{
            "name": "kimi", "base_url": "https://api.kimi.com/coding/v1",
            "api_key": "test-key", "api_mode": "chat_completions",
        }],
    }), encoding="utf-8")
    client, model = resolve_provider_client("custom:kimi", "kimi-for-coding")
    try:
        assert isinstance(client, _KimiAuxiliaryClient)
        assert "kimi.com/coding" in str(client.base_url)
        assert model == "kimi-for-coding"
    finally:
        if client:
            client.close()
