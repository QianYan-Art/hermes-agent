import pytest

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
    assert parse_context_window("256k") == 262_144
    assert parse_context_window("512k") == 524_288
    assert parse_context_window("1m") == 1_048_576
    assert parse_context_window("262,144") == 262_144
    assert parse_context_window("262_144") == 262_144


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" 512K ", 524_288),
        ("0.5m", 524_288),
        ("1.5M", 1_572_864),
        ("0.5k", 512),
        ("512000", 512_000),
        ("256000", 256_000),
    ],
)
def test_parse_context_window_binary_suffixes_preserve_bare_values(value, expected):
    assert parse_context_window(value) == expected


@pytest.mark.parametrize("value", ["", "0", "-1k", "512kb", "1g", "nan", "inf"])
def test_parse_context_window_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_context_window(value)


def test_context_window_default_constant():
    assert DEFAULT_CONTEXT_WINDOW == 256_000


def test_set_config_context_length_preserves_scalar_model():
    cfg = {"model": "old-model"}
    set_config_context_length(cfg, 256_000)
    assert cfg["model"]["default"] == "old-model"
    assert cfg["model"]["context_length"] == 256_000
