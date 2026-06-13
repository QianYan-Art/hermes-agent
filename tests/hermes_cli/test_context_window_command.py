from hermes_cli.commands import resolve_command
from hermes_cli.context_window import (
    DEFAULT_CONTEXT_WINDOW,
    parse_context_window,
    set_config_context_length,
)


def test_context_command_registered():
    cmd = resolve_command("context")
    assert cmd is not None
    assert cmd.name == "context"
    assert "--global" in cmd.args_hint


def test_parse_context_window_units():
    assert parse_context_window("256k") == 256_000
    assert parse_context_window("1m") == 1_000_000
    assert parse_context_window("262,144") == 262_144
    assert parse_context_window("262_144") == 262_144


def test_context_window_default_constant():
    assert DEFAULT_CONTEXT_WINDOW == 256_000


def test_set_config_context_length_preserves_scalar_model():
    cfg = {"model": "old-model"}
    set_config_context_length(cfg, 256_000)
    assert cfg["model"]["default"] == "old-model"
    assert cfg["model"]["context_length"] == 256_000
