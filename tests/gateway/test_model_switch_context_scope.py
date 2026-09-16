"""`/model` 切换时上下文窗口的作用域回归测试。

缺陷（2026-09）：``_auto_save_switch_context_length()`` 无条件调用
``_save_context_length_to_config()``，于是**会话级** ``/model`` 也会把探测到
的窗口写进全局 ``model.context_length``。对显式配置了窗口的部署（例如把
Kimi Code 限制为 262144，而接口自报 1M）来说，用户在 QQ 里临时切一次模型，
全局配置就被自动探测值覆盖了。

修复：与 ``/context`` 的语义对齐——只有 ``--global`` 才落盘，会话级切换不写
全局配置。
"""

from unittest.mock import patch

import pytest
import yaml

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource
from hermes_cli.model_switch import ModelSwitchResult


class _FakeModelInfo:
    context_window = 1_048_576
    max_output = 0

    def has_cost_data(self):
        return False

    def format_capabilities(self):
        return ""


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    runner._pending_model_notes = {}
    return runner


def _make_event(text):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="12345", chat_type="dm"),
    )


def _switch_result(model="kimi-for-coding", provider="custom"):
    return ModelSwitchResult(
        success=True,
        new_model=model,
        target_provider=provider,
        provider_changed=True,
        api_key="",
        base_url="https://api.kimi.com/coding/v1",
        api_mode="chat_completions",
        warning_message="",
        provider_label="kimi-code",
        resolved_via_alias=False,
        capabilities=None,
        model_info=_FakeModelInfo(),
        is_global=False,
    )


class _SpyRunner:
    """只暴露 ``_auto_save_switch_context_length`` 依赖的两个落地入口。"""

    def __init__(self):
        self.saved_global = []
        self.applied_session = []
        self._save_context_length_to_config = self.saved_global.append
        self._apply_context_length_to_cached_agent = (
            lambda session_key, value: self.applied_session.append((session_key, value))
        )

    def run(self, **kwargs):
        return GatewayRunner._auto_save_switch_context_length(
            self, _switch_result(), **kwargs
        )


def test_session_switch_does_not_write_global_context():
    spy = _SpyRunner()
    with patch(
        "hermes_cli.context_window.resolve_context_window"
    ) as resolve:
        resolve.return_value.value = 1_048_576
        value = spy.run(persist_global=False, session_key="tg:12345")

    assert value == 1_048_576
    assert spy.saved_global == [], "会话级切换不得写入全局 model.context_length"
    assert spy.applied_session == [("tg:12345", 1_048_576)]


def test_global_switch_writes_global_context():
    spy = _SpyRunner()
    with patch(
        "hermes_cli.context_window.resolve_context_window"
    ) as resolve:
        resolve.return_value.value = 1_048_576
        value = spy.run(persist_global=True, session_key="tg:12345")

    assert value == 1_048_576
    assert spy.saved_global == [1_048_576], "--global 切换仍应落盘"
    assert spy.applied_session == []


def test_session_switch_without_session_key_is_noop():
    """没有会话键时也不能退回去写全局配置。"""
    spy = _SpyRunner()
    with patch(
        "hermes_cli.context_window.resolve_context_window"
    ) as resolve:
        resolve.return_value.value = 262_144
        spy.run(persist_global=False, session_key="")

    assert spy.saved_global == []
    assert spy.applied_session == []


def _prepare_gateway(tmp_path, monkeypatch, persisted):
    """搭一个最小 gateway 运行环境，记录全局落盘调用。"""
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": {
                    "provider": "kimi-code",
                    "default": "kimi-for-coding",
                    "context_length": 262144,
                },
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
        ),
        encoding="utf-8",
    )

    import gateway.run as gateway_run
    import hermes_cli.model_switch as model_switch

    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    monkeypatch.setattr(
        model_switch, "switch_model", lambda **kwargs: _switch_result("k3", "custom")
    )

    runner = _make_runner()
    runner._evict_cached_agent = lambda session_key: None
    runner._save_context_length_to_config = persisted.append
    runner._apply_context_length_to_cached_agent = lambda session_key, value: None
    return runner


@pytest.mark.asyncio
async def test_handle_model_command_session_switch_keeps_config_context(
    tmp_path, monkeypatch
):
    persisted = []
    runner = _prepare_gateway(tmp_path, monkeypatch, persisted)

    reply = await runner._handle_model_command(_make_event("/model k3"))

    assert reply is not None
    assert persisted == [], "不带 --global 的 /model 不应改写全局上下文"
    assert "session only" in reply


@pytest.mark.asyncio
async def test_handle_model_command_global_switch_updates_config_context(
    tmp_path, monkeypatch
):
    persisted = []
    runner = _prepare_gateway(tmp_path, monkeypatch, persisted)

    reply = await runner._handle_model_command(_make_event("/model k3 --global"))

    assert reply is not None
    assert len(persisted) == 1, "--global 切换应写入全局上下文"
    assert "auto-saved" in reply
