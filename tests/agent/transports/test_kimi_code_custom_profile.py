"""验证命名自定义 provider 的 Kimi Code 请求参数与兼容边界。"""

import pytest

from agent.transports import get_transport
from providers import get_provider_profile


@pytest.fixture
def transport():
    import agent.transports.chat_completions  # noqa: F401

    return get_transport("chat_completions")


@pytest.fixture
def custom_profile():
    return get_provider_profile("custom")


def _build(transport, custom_profile, base_url, reasoning_config=None):
    return transport.build_kwargs(
        model="kimi-for-coding",
        messages=[{"role": "user", "content": "Hi"}],
        provider_profile=custom_profile,
        base_url=base_url,
        reasoning_config=reasoning_config,
    )


@pytest.mark.parametrize("path", ["/coding", "/coding/v1"])
@pytest.mark.parametrize(
    ("effort", "expected"),
    [
        ("minimal", "low"),
        ("low", "low"),
        ("medium", "high"),
        ("high", "high"),
        ("xhigh", "max"),
        ("max", "max"),
    ],
)
def test_kimi_code_reasoning_uses_supported_effort(
    transport, custom_profile, path, effort, expected
):
    kwargs = _build(
        transport,
        custom_profile,
        f"https://api.kimi.com{path}",
        {"effort": effort},
    )

    assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}
    assert kwargs["reasoning_effort"] == expected


def test_kimi_code_without_config_defaults_to_max(transport, custom_profile):
    kwargs = _build(transport, custom_profile, "https://api.kimi.com/coding/v1")

    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert kwargs["reasoning_effort"] == "max"


@pytest.mark.parametrize(
    "reasoning_config",
    [{"enabled": False, "effort": "high"}, {"effort": "none"}],
)
def test_kimi_code_disabled_thinking_omits_reasoning_effort(
    transport, custom_profile, reasoning_config
):
    kwargs = _build(
        transport,
        custom_profile,
        "https://api.kimi.com/coding/v1",
        reasoning_config,
    )

    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in kwargs


def test_kimi_code_lookalike_host_keeps_custom_behavior(transport, custom_profile):
    kwargs = _build(
        transport,
        custom_profile,
        "https://api.kimi.com.evil.example/coding/v1",
        {"effort": "low"},
    )

    assert "thinking" not in kwargs.get("extra_body", {})
    assert "reasoning_effort" not in kwargs


def test_ollama_custom_behavior_is_unchanged(transport, custom_profile):
    kwargs = transport.build_kwargs(
        model="qwen3",
        messages=[{"role": "user", "content": "Hi"}],
        provider_profile=custom_profile,
        base_url="http://127.0.0.1:11434/v1",
        ollama_num_ctx=32768,
        reasoning_config={"effort": "none"},
    )

    assert kwargs["extra_body"] == {
        "options": {"num_ctx": 32768},
        "think": False,
    }
    assert "reasoning_effort" not in kwargs
