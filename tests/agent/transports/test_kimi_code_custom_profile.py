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
    assert "prompt_cache_key" not in kwargs
    assert "extra_headers" not in kwargs


def test_kimi_session_key_is_stable_private_and_isolated(transport, custom_profile):
    def build(session_id):
        return transport.build_kwargs(
            model="kimi-for-coding",
            messages=[{"role": "user", "content": "测试"}],
            provider_profile=custom_profile,
            base_url="https://api.kimi.com/coding/v1",
            session_id=session_id,
            reasoning_config={"effort": "low"},
        )

    first = build("session-private-a")
    assert first["prompt_cache_key"] == build("session-private-a")["prompt_cache_key"]
    assert first["prompt_cache_key"] != build("session-private-b")["prompt_cache_key"]
    assert "session-private-a" not in first["prompt_cache_key"]
    assert first["extra_headers"]["User-Agent"].startswith("Tangyuge-Hermes/")
    assert "x-opencode-session" not in first["extra_headers"]


@pytest.mark.parametrize(
    "url",
    [
        "http://api.kimi.com/coding/v1",
        "https://api.kimi.com.evil.example/coding/v1",
        "https://api.kimi.com:444/coding/v1",
        "https://user@api.kimi.com/coding/v1",
        "https://api.kimi.com/v1",
        "https://api.kimi.com/coding/v1?route=other",
        "https://api.kimi.com:bad/coding/v1",
    ],
)
def test_kimi_identity_is_not_sent_to_other_endpoints(transport, custom_profile, url):
    kwargs = _build(transport, custom_profile, url, {"effort": "low"})
    assert "prompt_cache_key" not in kwargs
    assert "extra_headers" not in kwargs


def test_independent_kimi_calls_do_not_share_constant_cache_key(transport, custom_profile):
    first = _build(transport, custom_profile, "https://api.kimi.com/coding/v1")
    second = _build(transport, custom_profile, "https://api.kimi.com/coding/v1")
    assert first["prompt_cache_key"] != second["prompt_cache_key"]


def test_kimi_sdk_wire_headers_and_body(transport, custom_profile):
    """用真实 SDK 编码请求，验证身份、缓存键与历史回传。"""
    import json

    import httpx
    from openai import OpenAI

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "test",
            "object": "chat.completion",
            "created": 0,
            "model": "kimi-for-coding",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"},
                         "finish_reason": "stop"}],
        })

    history = [
        {"role": "system", "content": "稳定的基础提示"},
        {"role": "user", "content": "计算"},
        {"role": "assistant", "content": "2", "reasoning_content": "一次已完成的计算"},
        {"role": "user", "content": "解释"},
    ]
    kwargs = transport.build_kwargs(
        model="kimi-for-coding",
        messages=history,
        provider_profile=custom_profile,
        base_url="https://api.kimi.com/coding/v1",
        reasoning_config={"effort": "low"},
        session_id="wire-session",
    )
    with OpenAI(
        api_key="test-only",
        base_url="https://api.kimi.com/coding/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ) as client:
        client.chat.completions.create(**kwargs)
    sent = json.loads(requests[0].content)
    assert requests[0].headers["user-agent"].startswith("Tangyuge-Hermes/")
    assert "x-opencode-session" not in requests[0].headers
    assert sent["prompt_cache_key"] == kwargs["prompt_cache_key"]
    assert sent["reasoning_effort"] == "low"
    assert sent["thinking"]["type"] == "enabled"
    assert sent["messages"][2]["reasoning_content"] == "一次已完成的计算"
    assert history[2]["reasoning_content"] == "一次已完成的计算"
