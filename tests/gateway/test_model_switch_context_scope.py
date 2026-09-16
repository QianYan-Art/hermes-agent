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
        self._session_model_overrides = {}
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
    assert spy.applied_session == [("tg:12345", 1_048_576)]


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
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(
        "agent.model_metadata.fetch_endpoint_model_metadata",
        lambda *args, **kwargs: {"k3": {"context_length": 262144}},
    )
    monkeypatch.setattr("agent.model_metadata.save_context_length", lambda *args: None)
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
    assert "global)" in reply


@pytest.mark.asyncio
async def test_switch_stores_session_window_after_cache_eviction(tmp_path, monkeypatch):
    persisted = []
    runner = _prepare_gateway(tmp_path, monkeypatch, persisted)
    event = _make_event("/model k3")
    key = runner._session_key_for_source(event.source)
    await runner._handle_model_command(event)
    assert runner._session_model_overrides[key]["context_length"] == 262144
    assert runner._session_model_overrides[key]["context_source"] == "detected"
    assert persisted == []
    reply = await runner._handle_context_command(_make_event("/context"))
    assert "262,144" in reply
    assert "session:" in reply


def test_fresh_agent_receives_session_window_without_cache_entry():
    from types import SimpleNamespace
    from unittest.mock import Mock
    runner = _make_runner()
    agent = SimpleNamespace(
        _config_context_length=256000, context_compressor=Mock(),
        model="k3", provider="custom", _cached_system_prompt="frozen",
        _primary_runtime={"compressor_context_length": 256000},
    )
    runner._apply_context_length_to_cached_agent("test", 262144, agent=agent)
    assert agent._config_context_length == 262144
    assert agent.context_compressor.update_model.call_args.kwargs["context_length"] == 262144
    assert agent._primary_runtime["compressor_context_length"] == 262144
    agent._cached_system_prompt = "frozen"
    runner._apply_context_length_to_cached_agent("test", 262144, agent=agent)
    assert agent._cached_system_prompt == "frozen"
    assert agent.context_compressor.update_model.call_count == 1


@pytest.mark.asyncio
async def test_context_explicit_value_survives_absent_cached_agent(tmp_path, monkeypatch):
    runner = _prepare_gateway(tmp_path, monkeypatch, [])
    event = _make_event("/context 128k")
    reply = await runner._handle_context_command(event)
    key = runner._session_key_for_source(event.source)
    assert "131,072" in reply
    assert runner._session_model_overrides[key]["context_length"] == 131072
    assert "131,072" in await runner._handle_context_command(_make_event("/context"))


@pytest.mark.asyncio
async def test_offline_switch_retains_initial_per_model_config(tmp_path, monkeypatch):
    runner = _prepare_gateway(tmp_path, monkeypatch, [])
    path = tmp_path / ".hermes" / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    del cfg["model"]["context_length"]
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.setattr("agent.model_metadata.fetch_endpoint_model_metadata", lambda *a, **kw: {})
    monkeypatch.setattr("agent.model_metadata.get_cached_context_length", lambda *a: None)
    event = _make_event("/model k3")
    reply = await runner._handle_model_command(event)
    assert "262,144" in reply and "retained" in reply
    assert runner._session_model_overrides[runner._session_key_for_source(event.source)]["context_length"] == 262144


@pytest.mark.parametrize("explicit,expected", [(False, 131072), (True, 8192)])
def test_ollama_context_updates_request_unless_explicit(explicit, expected):
    from types import SimpleNamespace
    from unittest.mock import Mock
    runner = _make_runner()
    agent = SimpleNamespace(
        _config_context_length=256000, _ollama_num_ctx=8192,
        _ollama_num_ctx_explicit=explicit, context_compressor=Mock(),
        model="local-model", provider="custom", _cached_system_prompt="frozen",
    )
    runner._apply_context_length_to_cached_agent("test", 131072, agent=agent)
    assert agent._ollama_num_ctx == expected


@pytest.mark.parametrize("raw", ["- item\n", "a-string\n"])
def test_non_mapping_gateway_config_is_normalized(tmp_path, monkeypatch, raw):
    import gateway.run as gateway_run
    (tmp_path / "config.yaml").write_text(raw, encoding="utf-8")
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    assert gateway_run._load_gateway_config() == {}
