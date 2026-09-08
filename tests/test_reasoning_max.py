"""覆盖 max 等级的命令、配置、帮助和请求映射。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from hermes_constants import VALID_REASONING_EFFORTS, parse_reasoning_effort


def test_command_completion_includes_all_efforts():
    from hermes_cli.commands import COMMAND_REGISTRY

    command = next(item for item in COMMAND_REGISTRY if item.name == "reasoning")
    assert "max" in command.subcommands
    assert set(VALID_REASONING_EFFORTS).issubset(command.subcommands)


@pytest.mark.parametrize("saved", [True, False])
def test_cli_max_updates_agent_and_saves_config(monkeypatch, saved):
    import cli

    save = MagicMock(return_value=saved)
    monkeypatch.setattr(cli, "save_config_value", save)
    monkeypatch.setattr(cli, "_cprint", MagicMock())
    instance = SimpleNamespace(reasoning_config=None, show_reasoning=False, agent=MagicMock())

    cli.HermesCLI._handle_reasoning_command(instance, "/reasoning MAX")

    assert instance.reasoning_config == {"enabled": True, "effort": "max"}
    assert instance.agent is None
    assert instance.show_reasoning is False
    save.assert_called_once_with("agent.reasoning_effort", "max")


@pytest.mark.parametrize("command", ["/reasoning", "/reasoning invalid"])
def test_cli_help_lists_max(monkeypatch, command):
    import cli

    output = []
    monkeypatch.setattr(cli, "_cprint", output.append)
    save = MagicMock()
    monkeypatch.setattr(cli, "save_config_value", save)
    instance = SimpleNamespace(reasoning_config=None, show_reasoning=False, agent=None)

    cli.HermesCLI._handle_reasoning_command(instance, command)

    assert "max" in "\n".join(output)
    save.assert_not_called()
    assert instance.reasoning_config is None


@pytest.fixture
def qq_runner(tmp_path, monkeypatch):
    import gateway.run as gateway_run
    from gateway.config import Platform
    from gateway.platforms.base import MessageEvent
    from gateway.session import SessionSource

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "agent:\n  reasoning_effort: medium\nmodel:\n  default: minimax-m3\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    runner = object.__new__(gateway_run.GatewayRunner)
    runner._session_reasoning_overrides = {}
    runner._evict_cached_agent = MagicMock()
    source = SessionSource(platform=Platform.QQBOT, user_id="test-user", chat_id="test-chat")

    def event(text):
        return MessageEvent(text=text, source=source)

    return runner, event, config_path


@pytest.mark.asyncio
@pytest.mark.parametrize("argument", ["max", "MAX", "  max  "])
async def test_qq_max_is_session_only_and_reset_restores_default(qq_runner, argument):
    runner, event, config_path = qq_runner
    original = config_path.read_bytes()
    message = event(f"/reasoning {argument}")
    session_key = runner._session_key_for_source(message.source)

    await runner._handle_reasoning_command(message)

    expected = {"enabled": True, "effort": "max"}
    assert runner._session_reasoning_overrides[session_key] == expected
    assert runner._resolve_session_reasoning_config(source=message.source) == expected
    runner._evict_cached_agent.assert_called_once_with(session_key)
    assert config_path.read_bytes() == original
    assert "`max`" in await runner._handle_reasoning_command(event("/reasoning"))

    await runner._handle_reasoning_command(event("/reasoning reset"))

    assert session_key not in runner._session_reasoning_overrides
    assert runner._resolve_session_reasoning_config(source=message.source) == {
        "enabled": True, "effort": "medium",
    }
    assert config_path.read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("argument", ["max --global", "--global max"])
async def test_qq_max_global_round_trip(qq_runner, argument):
    runner, event, config_path = qq_runner
    message = event(f"/reasoning {argument}")
    session_key = runner._session_key_for_source(message.source)
    runner._session_reasoning_overrides[session_key] = {"enabled": True, "effort": "low"}

    await runner._handle_reasoning_command(message)

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config == {"agent": {"reasoning_effort": "max"}, "model": {"default": "minimax-m3"}}
    assert session_key not in runner._session_reasoning_overrides
    assert runner._load_reasoning_config() == {"enabled": True, "effort": "max"}
    runner._evict_cached_agent.assert_called_once_with(session_key)


@pytest.mark.parametrize("locale_path", sorted((Path(__file__).parents[1] / "locales").glob("*.yaml")),
                         ids=lambda path: path.stem)
def test_gateway_locale_help_lists_max(locale_path):
    catalog = yaml.safe_load(locale_path.read_text(encoding="utf-8"))
    messages = catalog["gateway"]["reasoning"]
    assert "|xhigh|max|" in messages["status"]
    assert "xhigh, max\n" in messages["unknown_arg"]


@pytest.mark.parametrize("effort,budget", [("medium", 8000), ("xhigh", 32000), ("max", 32000)])
def test_minimax_manual_budget_keeps_existing_limit(effort, budget):
    from agent.anthropic_adapter import build_anthropic_kwargs

    kwargs = build_anthropic_kwargs(
        model="minimax-m3",
        base_url="https://api.minimaxi.com/anthropic",
        messages=[{"role": "user", "content": "test"}],
        tools=None,
        max_tokens=4096,
        reasoning_config=parse_reasoning_effort(effort),
    )

    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": budget}
    assert kwargs["max_tokens"] >= budget + 4096
    assert "output_config" not in kwargs


def test_max_reaches_adaptive_request_without_becoming_xhigh():
    from agent.anthropic_adapter import build_anthropic_kwargs

    kwargs = build_anthropic_kwargs(
        model="claude-opus-4-7",
        messages=[{"role": "user", "content": "test"}],
        tools=None,
        max_tokens=4096,
        reasoning_config=parse_reasoning_effort("max"),
    )

    assert kwargs["output_config"] == {"effort": "max"}
    assert kwargs["thinking"]["type"] == "adaptive"
