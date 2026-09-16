"""CLI 侧 `/model` 切换的上下文作用域回归测试。

与 ``tests/gateway/test_model_switch_context_scope.py`` 同一个缺陷：
``HermesCLI._auto_persist_context_window()`` 过去无条件写
``model.context_length``，会话级切换也会覆盖显式配置的窗口。修复后只有
``--global`` 落盘，会话级切换仅作用于当前进程的 agent。
"""

from unittest.mock import patch

from hermes_cli.model_switch import ModelSwitchResult


class _FakeModelInfo:
    context_window = 1_048_576
    max_output = 0

    def has_cost_data(self):
        return False

    def format_capabilities(self):
        return ""


class _StubCLI:
    agent = None
    model = ""
    provider = ""
    api_key = ""
    base_url = ""
    api_mode = ""


def _result():
    return ModelSwitchResult(
        success=True,
        new_model="kimi-for-coding",
        target_provider="custom",
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


def _run(monkeypatch, persist_global):
    import cli as cli_mod

    saved = []
    runtime = []
    stub = _StubCLI()
    stub._current_context_config = lambda: ({}, [])
    stub._set_runtime_context_window = runtime.append
    monkeypatch.setattr(cli_mod, "save_config_value", lambda *a, **k: saved.append(a) or True)
    with patch("agent.model_metadata.get_model_context_length", return_value=1_048_576):
        value = cli_mod.HermesCLI._auto_persist_context_window(stub, _result(), persist_global)
    return value, saved, runtime


def test_cli_session_switch_does_not_write_config(monkeypatch):
    value, saved, runtime = _run(monkeypatch, False)

    assert value == 1_048_576
    assert saved == [], "会话级切换不得写入 model.context_length"
    assert runtime == [1_048_576], "当前进程的 agent 仍应用新窗口"


def test_cli_global_switch_writes_config(monkeypatch):
    value, saved, runtime = _run(monkeypatch, True)

    assert value == 1_048_576
    assert saved == [("model.context_length", 1_048_576)]
    assert runtime == [1_048_576]


def test_cli_defaults_to_session_scope(monkeypatch):
    """省略参数时按会话级处理，避免旧调用点意外落盘。"""
    import cli as cli_mod

    saved = []
    stub = _StubCLI()
    stub._current_context_config = lambda: ({}, [])
    stub._set_runtime_context_window = lambda value: None
    monkeypatch.setattr(cli_mod, "save_config_value", lambda *a, **k: saved.append(a) or True)
    with patch("agent.model_metadata.get_model_context_length", return_value=262_144):
        cli_mod.HermesCLI._auto_persist_context_window(stub, _result())

    assert saved == []
