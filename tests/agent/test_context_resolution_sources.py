"""窗口来源与 Kimi 精确模型元数据的离线回归。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from agent import model_metadata as metadata
from hermes_cli.context_window import resolve_context_window

BASE = "https://api.kimi.com/coding/v1"


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(metadata, "_endpoint_model_metadata_cache", {})
    monkeypatch.setattr(metadata, "_endpoint_model_metadata_cache_time", {})
    monkeypatch.setattr(metadata, "get_cached_context_length", lambda *args: None)
    monkeypatch.setattr(metadata, "save_context_length", Mock())
    monkeypatch.setattr(metadata, "_query_ollama_api_show", Mock(side_effect=AssertionError("不应向 Kimi 发 Ollama 探测")))
    monkeypatch.setattr(metadata.requests, "get", Mock(side_effect=requests.ConnectionError("offline")))


def models_response(monkeypatch, data):
    get = Mock(return_value=SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"data": data},
    ))
    monkeypatch.setattr(metadata.requests, "get", get)
    return get


def resolve(**kwargs):
    return resolve_context_window(
        model="k3-256k", provider="custom", base_url=BASE,
        use_config_override=False, **kwargs,
    )


def test_official_model_context_beats_cache_and_uses_real_identity(monkeypatch):
    get = models_response(monkeypatch, [
        {"id": "kimi-for-coding", "context_length": 1048576},
        {"id": "k3-256k", "context_length": 262144},
    ])
    monkeypatch.setattr(metadata, "get_cached_context_length", lambda *args: 256000)
    result = resolve(api_key="test-only")
    assert (result.value, result.source) == (262144, "detected")
    assert get.call_args.args[0] == BASE + "/models"
    assert get.call_args.kwargs["headers"]["User-Agent"].startswith("Tangyuge-Hermes/")
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer test-only"
    metadata.save_context_length.assert_called_once_with("k3-256k", BASE, 262144)


@pytest.mark.parametrize("data", [
    [{"id": "kimi-for-coding", "context_length": 1048576}],
    [{"id": "k3", "context_length": 1048576}],
    [{"id": "k3-256k", "context_length": 0}],
])
def test_does_not_borrow_another_models_limit(monkeypatch, data):
    models_response(monkeypatch, data)
    result = resolve()
    assert (result.value, result.source) == (256000, "fallback")


def test_explicit_model_limit_beats_official_response(monkeypatch):
    get = models_response(monkeypatch, [{"id": "k3-256k", "context_length": 1048576}])
    result = resolve(custom_providers=[{
        "name": "kimi-code", "base_url": BASE,
        "models": {"k3-256k": {"context_length": 262144}},
    }])
    assert (result.value, result.source) == (262144, "model_config")
    get.assert_not_called()


def test_unknown_context_retains_explicit_value():
    result = resolve(fallback_context_length=131072)
    assert (result.value, result.source) == (131072, "retained")


def test_fallback_value_is_not_detected():
    result = resolve()
    assert (result.value, result.source) == (256000, "fallback")


def test_real_256000_response_is_detected(monkeypatch):
    models_response(monkeypatch, [{"id": "k3-256k", "context_length": 256000}])
    assert resolve().source == "detected"


def test_known_cache_is_usable_when_endpoint_offline(monkeypatch):
    monkeypatch.setattr(metadata, "get_cached_context_length", lambda *args: 262144)
    assert (resolve().value, resolve().source) == (262144, "detected")


def test_legacy_callers_keep_default_while_source_aware_callers_get_none():
    assert metadata.get_model_context_length("k3-256k", base_url=BASE) == 256000
    assert metadata.get_model_context_length("k3-256k", base_url=BASE, allow_fallback=False) is None


def test_explicit_global_context_is_not_probed(monkeypatch):
    result = resolve_context_window(
        model="k3-256k", base_url=BASE,
        config={"model": {"context_length": 131072}},
    )
    assert (result.value, result.source) == (131072, "config")
    metadata.requests.get.assert_not_called()
