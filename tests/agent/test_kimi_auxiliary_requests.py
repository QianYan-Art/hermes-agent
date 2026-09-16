import json

import httpx
import pytest
from openai import AsyncOpenAI, OpenAI

from agent import auxiliary_client as aux
from hermes_cli import __version__


KIMI_BASE_URL = "https://api.kimi.com/coding/v1"
MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"


def _completion_payload():
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "kimi-k2",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _recording_handler(records, *, fail_first=False):
    def handler(request: httpx.Request):
        records.append((request, json.loads(request.content)))
        if fail_first and len(records) == 1:
            return httpx.Response(
                400,
                request=request,
                json={"error": {"message": "temperature is unsupported"}},
            )
        return httpx.Response(200, request=request, json=_completion_payload())

    return handler


def _assert_kimi_request(request, payload):
    assert request.url.path == "/coding/v1/chat/completions"
    assert request.headers["user-agent"] == f"Tangyuge-Hermes/{__version__}"
    assert request.headers.get_list("user-agent") == [f"Tangyuge-Hermes/{__version__}"]
    assert payload["prompt_cache_key"].startswith("hermes-")


def test_direct_sync_kimi_client_injects_request_metadata_and_isolates_calls():
    records = []
    transport = httpx.MockTransport(_recording_handler(records))
    real_client = OpenAI(
        api_key="test-key",
        base_url=KIMI_BASE_URL,
        http_client=httpx.Client(transport=transport),
    )
    client = aux._KimiAuxiliaryClient(real_client)

    try:
        client.chat.completions.create(
            model="kimi-k2",
            messages=[{"role": "user", "content": "one"}],
            extra_headers={"user-agent": "spoofed", "X-Test-Header": "keep"},
        )
        client.chat.completions.create(
            model="kimi-k2",
            messages=[{"role": "user", "content": "two"}],
        )
    finally:
        client.close()

    assert len(records) == 2
    for request, payload in records:
        _assert_kimi_request(request, payload)
    assert records[0][0].headers["x-test-header"] == "keep"
    assert records[0][1]["prompt_cache_key"] != records[1][1]["prompt_cache_key"]


@pytest.mark.asyncio
async def test_direct_async_kimi_client_injects_request_metadata():
    records = []
    transport = httpx.MockTransport(_recording_handler(records))
    real_client = AsyncOpenAI(
        api_key="test-key",
        base_url=KIMI_BASE_URL,
        http_client=httpx.AsyncClient(transport=transport),
    )
    client = aux._AsyncKimiAuxiliaryClient(real_client)

    try:
        await client.chat.completions.create(
            model="kimi-k2",
            messages=[{"role": "user", "content": "async"}],
            extra_headers={"user-agent": "spoofed", "X-Test-Header": "keep"},
        )
    finally:
        await client.close()

    assert len(records) == 1
    _assert_kimi_request(*records[0])
    assert records[0][0].headers["x-test-header"] == "keep"


def test_build_call_kwargs_only_targets_kimi_code_endpoint():
    kimi_kwargs = aux._build_call_kwargs(
        "custom",
        "kimi-k2",
        [{"role": "user", "content": "hello"}],
        base_url=KIMI_BASE_URL,
        kimi_request_options={
            "extra_headers": {"User-Agent": "Tangyuge-Hermes/test"},
            "prompt_cache_key": "hermes-fixed",
        },
    )
    moonshot_kwargs = aux._build_call_kwargs(
        "custom",
        "moonshot-v1",
        [{"role": "user", "content": "hello"}],
        base_url=MOONSHOT_BASE_URL,
    )

    assert kimi_kwargs["extra_headers"] == {"User-Agent": "Tangyuge-Hermes/test"}
    assert kimi_kwargs["prompt_cache_key"] == "hermes-fixed"
    assert "extra_headers" not in moonshot_kwargs
    assert "prompt_cache_key" not in moonshot_kwargs


def test_call_llm_reuses_one_kimi_key_across_retry(monkeypatch):
    records = []
    transport = httpx.MockTransport(_recording_handler(records, fail_first=True))
    real_client = OpenAI(
        api_key="test-key",
        base_url=KIMI_BASE_URL,
        http_client=httpx.Client(transport=transport),
    )
    client = aux._KimiAuxiliaryClient(real_client)
    monkeypatch.setattr(
        aux,
        "_resolve_task_provider_model",
        lambda *args, **kwargs: ("custom", "kimi-k2", KIMI_BASE_URL, "test-key", None),
    )
    monkeypatch.setattr(aux, "_get_cached_client", lambda *args, **kwargs: (client, "kimi-k2"))
    monkeypatch.setattr(aux, "_fixed_temperature_for_model", lambda *args: None)
    monkeypatch.setattr(aux, "_is_unsupported_temperature_error", lambda error: True)

    try:
        response = aux.call_llm(
            provider="custom",
            model="kimi-k2",
            base_url=KIMI_BASE_URL,
            api_key="test-key",
            messages=[{"role": "user", "content": "retry"}],
            temperature=0.2,
        )
    finally:
        client.close()

    assert response.choices[0].message.content == "ok"
    assert len(records) == 2
    assert records[0][1]["prompt_cache_key"] == records[1][1]["prompt_cache_key"]


@pytest.mark.asyncio
async def test_async_call_llm_reuses_one_kimi_key_across_retry(monkeypatch):
    records = []
    transport = httpx.MockTransport(_recording_handler(records, fail_first=True))
    real_client = AsyncOpenAI(
        api_key="test-key",
        base_url=KIMI_BASE_URL,
        http_client=httpx.AsyncClient(transport=transport),
    )
    client = aux._AsyncKimiAuxiliaryClient(real_client)
    monkeypatch.setattr(
        aux,
        "_resolve_task_provider_model",
        lambda *args, **kwargs: ("custom", "kimi-k2", KIMI_BASE_URL, "test-key", None),
    )
    monkeypatch.setattr(aux, "_get_cached_client", lambda *args, **kwargs: (client, "kimi-k2"))
    monkeypatch.setattr(aux, "_fixed_temperature_for_model", lambda *args: None)
    monkeypatch.setattr(aux, "_is_unsupported_temperature_error", lambda error: True)

    try:
        response = await aux.async_call_llm(
            provider="custom",
            model="kimi-k2",
            base_url=KIMI_BASE_URL,
            api_key="test-key",
            messages=[{"role": "user", "content": "async retry"}],
            temperature=0.2,
        )
    finally:
        await client.close()

    assert response.choices[0].message.content == "ok"
    assert len(records) == 2
    assert records[0][1]["prompt_cache_key"] == records[1][1]["prompt_cache_key"]
