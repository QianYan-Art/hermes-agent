"""Kimi 缓存用量兼容与去重回归。"""

from types import SimpleNamespace

import pytest

from agent.transports.chat_completions import ChatCompletionsTransport
from agent.usage_pricing import normalize_usage


@pytest.mark.parametrize("nested", [None, 0, 600])
def test_kimi_cache_usage_shapes(nested):
    details = None if nested is None else SimpleNamespace(cached_tokens=nested)
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=20,
        cached_tokens=500,
        prompt_tokens_details=details,
    )
    expected = nested or 500
    normalized = normalize_usage(usage, provider="custom", api_mode="chat_completions")
    assert normalized.cache_read_tokens == expected
    assert normalized.input_tokens == 1000 - expected
    assert normalized.output_tokens == 20
    assert ChatCompletionsTransport().extract_cache_stats(SimpleNamespace(usage=usage)) == {
        "cached_tokens": expected,
        "creation_tokens": 0,
    }


def test_no_cache_statistics_are_not_fabricated():
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=20)
    assert normalize_usage(usage, api_mode="chat_completions").cache_read_tokens == 0
    assert ChatCompletionsTransport().extract_cache_stats(SimpleNamespace(usage=usage)) is None
