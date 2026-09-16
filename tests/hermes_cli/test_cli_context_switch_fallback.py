"""CLI /model 上下文窗口作用域与来源回归测试。"""

from __future__ import annotations

from unittest.mock import patch

from hermes_cli.context_window import ContextWindowResult
from hermes_cli.model_switch import ModelSwitchResult


class _FakeCompressor:
    def __init__(self, context_length=256_000):
        self.context_length = context_length
        self.last_update = None

    def update_model(self, **kwargs):
        self.last_update = kwargs
        self.context_length = kwargs["context_length"]


class _FakeAgent:
    def __init__(self, config_context_length=None):
        self.model = "old-model"
        self.provider = "old-provider"
        self.base_url = "https://old.invalid/v1"
        self.api_key = "old-key"
        self.api_mode = "chat_completions"
        self._config_context_length = config_context_length
        self.context_compressor = _FakeCompressor()
        self._primary_runtime = {"compressor_context_length": 256_000}
        self._cached_system_prompt = "cached"

    def switch_model(self, new_model, new_provider, api_key="", base_url="", api_mode=""):
        self.model = new_model
        self.provider = new_provider
        self.api_key = api_key
        self.base_url = base_url
        self.api_mode = api_mode


def _make_cli(config=None, config_context_length=None):
    import cli as cli_mod

    cli = object.__new__(cli_mod.HermesCLI)
    cli.agent = _FakeAgent(config_context_length)
    cli.model = "old-model"
    cli.provider = "old-provider"
    cli.requested_provider = "old-provider"
    cli.api_key = "old-key"
    cli.base_url = "https://old.invalid/v1"
    cli.api_mode = "chat_completions"
    cli._explicit_api_key = "old-key"
    cli._explicit_base_url = cli.base_url
    cli._pending_model_switch_note = ""
    cli._session_context_length = None
    cli._session_context_source = None
    cli._global_context_source = None
    cli._last_context_window_source = None
    cli._current_context_config = lambda: (config or {}, [])
    return cli


def _switch_result():
    return ModelSwitchResult(
        success=True,
        new_model="new-model",
        target_provider="new-provider",
        provider_changed=True,
        api_key="new-key",
        base_url="https://new.invalid/v1",
        api_mode="chat_completions",
        provider_label="New Provider",
        model_info=None,
    )


def test_model_switch_passes_previous_explicit_context_as_retained_fallback():
    import cli as cli_mod

    cli = _make_cli(config_context_length=180_000)
    resolved = ContextWindowResult(180_000, "retained")
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=resolved,
    ) as resolve, patch("cli.save_config_value") as save:
        value = cli_mod.HermesCLI._auto_persist_context_window(
            cli, _switch_result(), persist_global=False
        )

    assert value == 180_000
    assert resolve.call_args.kwargs["use_config_override"] is False
    assert resolve.call_args.kwargs["fallback_context_length"] == 180_000
    save.assert_not_called()
    assert cli.agent.context_compressor.context_length == 180_000
    assert cli.agent._primary_runtime["compressor_context_length"] == 180_000
    assert cli._last_context_window_source == "retained"


def test_detected_default_is_not_reused_as_custom_fallback():
    import cli as cli_mod

    cli = _make_cli(config_context_length=None)
    cli.agent.context_compressor.context_length = 256_000
    resolved = ContextWindowResult(256_000, "fallback")
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=resolved,
    ) as resolve:
        value = cli_mod.HermesCLI._auto_persist_context_window(
            cli, _switch_result(), persist_global=False
        )

    assert value == 256_000
    assert resolve.call_args.kwargs["fallback_context_length"] is None
    assert cli._last_context_window_source == "fallback"
    assert cli_mod.HermesCLI._current_context_fallback(cli) is None


def test_global_save_failure_does_not_skip_runtime_context_update():
    import cli as cli_mod

    cli = _make_cli(config_context_length=180_000)
    resolved = ContextWindowResult(180_000, "retained")
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=resolved,
    ), patch("cli.save_config_value", return_value=False) as save:
        value = cli_mod.HermesCLI._auto_persist_context_window(
            cli, _switch_result(), persist_global=True
        )

    assert value == 180_000
    assert cli.agent.context_compressor.context_length == 180_000
    save.assert_called_once_with("model.context_length", 180_000)
    assert cli._last_context_persisted is False
    assert cli._last_context_persist_error == "save_config_value returned False"


def test_model_switch_display_includes_context_source(monkeypatch):
    import cli as cli_mod

    cli = _make_cli(config_context_length=180_000)
    captured = []
    monkeypatch.setattr(cli_mod, "_cprint", lambda value, *args, **kwargs: captured.append(str(value)))
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=ContextWindowResult(180_000, "retained"),
    ), patch("cli.save_config_value", return_value=False):
        cli_mod.HermesCLI._apply_model_switch_result(cli, _switch_result(), False)

    context_line = next(line for line in captured if "Context:" in line)
    assert "180,000" in context_line
    assert "retained" in context_line
    assert "session only" in context_line


def test_context_auto_uses_source_instead_of_256k_value(monkeypatch):
    import cli as cli_mod

    cli = _make_cli()
    captured = []
    monkeypatch.setattr(cli_mod, "_cprint", lambda value, *args, **kwargs: captured.append(str(value)))
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=ContextWindowResult(256_000, "detected"),
    ) as resolve:
        cli_mod.HermesCLI._handle_context_command(cli, "/context auto")

    assert "fallback_context_length" not in resolve.call_args.kwargs
    assert not any("Auto-detect" in line for line in captured)


def test_context_auto_reports_fallback_with_exact_token_units(monkeypatch):
    import cli as cli_mod

    cli = _make_cli()
    captured = []
    monkeypatch.setattr(cli_mod, "_cprint", lambda value, *args, **kwargs: captured.append(str(value)))
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=ContextWindowResult(256_000, "fallback"),
    ) as resolve:
        cli_mod.HermesCLI._handle_context_command(cli, "/context auto")

    assert "fallback_context_length" not in resolve.call_args.kwargs
    assert any("Auto-detect unavailable: default 256,000 tokens (250K)" in line for line in captured)


def test_context_without_args_prefers_session_value_before_agent_creation(monkeypatch):
    import cli as cli_mod

    cli = _make_cli(config={"model": {"context_length": 320_000}})
    cli.agent = None
    cli._session_context_length = 180_000
    cli._session_context_source = "retained"
    captured = []
    monkeypatch.setattr(cli_mod, "_cprint", lambda value, *args, **kwargs: captured.append(str(value)))
    with patch("hermes_cli.context_window.resolve_context_window") as resolve:
        cli_mod.HermesCLI._handle_context_command(cli, "/context")

    resolve.assert_not_called()
    assert captured[0] == "  Context: 180,000 tokens (retained)"


def test_global_model_switch_uses_global_config_as_fallback(monkeypatch):
    import cli as cli_mod

    cli = _make_cli(
        config={"model": {"context_length": 320_000}},
        config_context_length=180_000,
    )
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=ContextWindowResult(320_000, "retained"),
    ) as resolve, patch("cli.save_config_value", return_value=True):
        value = cli_mod.HermesCLI._auto_persist_context_window(
            cli, _switch_result(), persist_global=True
        )

    assert value == 320_000
    assert resolve.call_args.kwargs["fallback_context_length"] == 320_000


def test_global_model_switch_reports_context_save_failure_without_auto_saved(
    monkeypatch,
):
    import cli as cli_mod

    cli = _make_cli(config_context_length=180_000)
    captured = []
    monkeypatch.setattr(cli_mod, "_cprint", lambda value, *args, **kwargs: captured.append(str(value)))
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=ContextWindowResult(180_000, "retained"),
    ), patch("cli.save_config_value", return_value=False):
        cli_mod.HermesCLI._apply_model_switch_result(cli, _switch_result(), True)

    context_line = next(line for line in captured if "Context:" in line)
    assert "180,000" in context_line
    assert "global save failed" in context_line
    assert "auto-saved" not in context_line
    assert any("Failed to save model.context_length (--global)" in line for line in captured)


def test_global_model_switch_reports_context_save_exception(monkeypatch):
    import cli as cli_mod

    cli = _make_cli(config_context_length=180_000)
    captured = []
    monkeypatch.setattr(cli_mod, "_cprint", lambda value, *args, **kwargs: captured.append(str(value)))
    with patch(
        "hermes_cli.context_window.resolve_context_window",
        return_value=ContextWindowResult(180_000, "retained"),
    ), patch(
        "cli.save_config_value",
        side_effect=[OSError("disk full"), True, True],
    ):
        cli_mod.HermesCLI._apply_model_switch_result(cli, _switch_result(), True)

    assert cli.agent.context_compressor.context_length == 180_000
    assert any("Failed to save model.context_length (--global): disk full" in line for line in captured)
    assert not any("auto-saved" in line for line in captured if "Context:" in line)
