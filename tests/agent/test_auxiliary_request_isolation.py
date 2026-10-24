"""辅助请求的会话路由与调用方数据隔离回归，不访问外部服务。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent import auxiliary_client as aux


def _response(content):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason="stop",
    )])


@pytest.mark.asyncio
@pytest.mark.parametrize("auto_fallback", [False, True])
async def test_async_requests_keep_separate_session_routes(monkeypatch, auto_fallback):
    """不同会话的 auto 客户端缓存和首选失败后的解析都使用各自运行时。"""
    monkeypatch.setattr(aux, "_client_cache", {})
    monkeypatch.setattr(aux, "_pool_cache_hint", lambda *a, **kw: ())
    monkeypatch.setattr(aux, "_peek_pool_entry", lambda *a: None)
    monkeypatch.setattr(aux, "_get_task_extra_body", lambda task: {})

    def resolve(provider, model, async_mode, **kwargs):
        if provider == "custom":
            return None, None
        runtime = kwargs.get("main_runtime") or {}
        selected = runtime.get("model", "global-model")
        client = SimpleNamespace(
            base_url=runtime.get("base_url", "https://global.invalid/v1"),
            chat=SimpleNamespace(completions=SimpleNamespace(
                create=AsyncMock(return_value=_response(selected)),
            )),
        )
        return client, selected

    monkeypatch.setattr(aux, "resolve_provider_client", resolve)

    async def invoke(label):
        response = await aux.async_call_llm(
            provider="custom" if auto_fallback else "auto",
            main_runtime={
                "provider": "custom", "model": label,
                "base_url": f"https://{label}.invalid/v1", "api_key": f"key-{label}",
            },
            messages=[{"role": "user", "content": "检查当前路由"}],
        )
        return response.choices[0].message.content

    assert await asyncio.gather(invoke("session-a"), invoke("session-b")) == [
        "session-a", "session-b",
    ]
    assert await invoke("session-a") == "session-a"


@pytest.mark.asyncio
async def test_async_auth_recovery_keeps_session_route(monkeypatch):
    """凭据刷新后的客户端重建不能落回全局模型。"""
    monkeypatch.setattr(aux, "_client_cache", {})
    monkeypatch.setattr(aux, "_pool_cache_hint", lambda *a, **kw: ())
    monkeypatch.setattr(aux, "_peek_pool_entry", lambda *a: None)
    monkeypatch.setattr(aux, "_get_task_extra_body", lambda task: {})
    failure = RuntimeError("unauthorized")
    failure.status_code = 401
    calls = []

    def resolve(provider, model, async_mode, **kwargs):
        runtime = kwargs.get("main_runtime") or {}
        selected = runtime.get("model", "global-model")
        create = AsyncMock(
            side_effect=failure if not calls else None,
            return_value=_response(selected),
        )
        client = SimpleNamespace(
            base_url="https://session.invalid/v1",
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        )
        calls.append(client)
        return client, selected

    def refresh(provider):
        aux._evict_cached_client_instance(calls[-1])
        return True

    monkeypatch.setattr(aux, "resolve_provider_client", resolve)
    monkeypatch.setattr(aux, "_refresh_provider_credentials", refresh)
    response = await aux.async_call_llm(
        provider="custom",
        main_runtime={"provider": "custom", "model": "session-model"},
        messages=[{"role": "user", "content": "重试保持当前会话"}],
    )
    assert response.choices[0].message.content == "session-model"
    assert len(calls) == 2


def test_request_tags_do_not_mutate_caller_or_accumulate_on_retry(monkeypatch):
    """构建重试请求时保留输入标签，不能把 portal 标签反复写回调用方。"""
    monkeypatch.setattr(aux, "_nous_portal_tags", Mock(return_value=["portal"]))
    extra_body = {"tags": ["caller"]}
    first = aux._build_call_kwargs("nous", "model", [], extra_body=extra_body)
    second = aux._build_call_kwargs("nous", "model", [], extra_body=extra_body)
    assert extra_body == {"tags": ["caller"]}
    assert first["extra_body"]["tags"] == ["caller", "portal"]
    assert second["extra_body"]["tags"] == ["caller", "portal"]


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("runtime_provider", ["custom", "custom:session"])
async def test_capacity_fallback_uses_current_session_endpoint(monkeypatch, asynchronous, runtime_provider):
    """明确辅助后端故障后，主模型兜底须仍使用当前会话端点和凭据。"""
    failure = RuntimeError("connection refused")
    failing_create = AsyncMock(side_effect=failure) if asynchronous else Mock(side_effect=failure)
    failing_client = SimpleNamespace(
        base_url="https://aux.invalid/v1",
        chat=SimpleNamespace(completions=SimpleNamespace(create=failing_create)),
    )
    monkeypatch.setattr(aux, "_get_cached_client", lambda *a, **kw: (failing_client, "aux-model"))
    monkeypatch.setattr(aux, "_get_task_extra_body", lambda task: {})
    monkeypatch.setattr(aux, "_try_configured_fallback_chain", lambda *a, **kw: (None, None, ""))
    monkeypatch.setattr(aux, "_read_main_provider", lambda: "custom")
    monkeypatch.setattr(aux, "_read_main_model", lambda: "global-model")
    monkeypatch.setattr(aux, "_is_provider_unhealthy", lambda provider: False)
    runtime = {
        "provider": runtime_provider, "model": "session-model",
        "base_url": "https://session.invalid/v1", "api_key": "session-key",
        "api_mode": "chat_completions",
    }
    resolved = []

    def resolve(*args, **kwargs):
        resolved.append(kwargs)
        return SimpleNamespace(
            base_url=kwargs.get("explicit_base_url", "https://global.invalid/v1"),
            chat=SimpleNamespace(completions=SimpleNamespace(
                create=Mock(return_value=_response(kwargs["model"])),
            )),
        ), kwargs["model"]

    def to_async(client, model, **kwargs):
        result = client.chat.completions.create.return_value
        client.chat.completions.create = AsyncMock(return_value=result)
        return client, model

    monkeypatch.setattr(aux, "resolve_provider_client", resolve)
    monkeypatch.setattr(aux, "_to_async_client", to_async)
    kwargs = dict(provider="minimax", main_runtime=runtime, messages=[])
    response = await aux.async_call_llm(**kwargs) if asynchronous else aux.call_llm(**kwargs)
    assert response.choices[0].message.content == "session-model"
    assert resolved[0]["provider"] == "custom"
    assert resolved[0]["explicit_base_url"] == runtime["base_url"]
    assert resolved[0]["explicit_api_key"] == runtime["api_key"]
    assert resolved[0]["api_mode"] == runtime["api_mode"]
