"""Tests for the bundled rtk-rewrite plugin."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import yaml

from hermes_cli.plugins import PluginManager


PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "rtk-rewrite"


def _load_rtk_plugin():
    spec = importlib.util.spec_from_file_location("rtk_rewrite_test", PLUGIN_DIR / "__init__.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.reset_state_for_tests()
    return module


def test_manifest_is_bundled_standalone_plugin():
    manifest = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8"))

    assert manifest["name"] == "rtk-rewrite"
    assert manifest["kind"] == "standalone"
    assert "pre_tool_call" in manifest["provides_hooks"]


def test_bundled_plugin_discovery_can_find_rtk_rewrite(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump({"plugins": {"enabled": ["rtk-rewrite"]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr("shutil.which", lambda name: None if name == "rtk" else "bin")

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["rtk-rewrite"]
    assert loaded.manifest.source == "bundled"
    assert loaded.enabled
    assert not manager.has_hook("pre_tool_call")


def test_missing_rtk_binary_fails_open_and_warns_once(monkeypatch, capsys):
    module = _load_rtk_plugin()
    registered = []
    monkeypatch.setattr(module.shutil, "which", lambda name: None)

    module.register(SimpleNamespace(register_hook=lambda *args: registered.append(args)))
    module.register(SimpleNamespace(register_hook=lambda *args: registered.append(args)))

    err = capsys.readouterr().err
    assert registered == []
    assert err.count("rtk binary not found in PATH; Hermes hook not registered") == 1


def test_rewrite_hook_passes_through_expected_rtk_exit(monkeypatch):
    module = _load_rtk_plugin()
    args = {"command": "ls"}
    result = SimpleNamespace(returncode=1, stdout="rm -rf /", stderr="")
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: result)

    module._pre_tool_call(tool_name="terminal", args=args)

    assert args["command"] == "ls"


def test_rewrite_hook_updates_command_on_accepted_result(monkeypatch):
    module = _load_rtk_plugin()
    args = {"command": "ls"}
    result = SimpleNamespace(returncode=0, stdout="ls -la\n", stderr="")
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: result)

    module._pre_tool_call(tool_name="terminal", args=args)

    assert args["command"] == "ls -la"


def test_rewrite_hook_fails_open_on_runtime_error(monkeypatch, capsys):
    module = _load_rtk_plugin()
    args = {"command": "ls"}

    def raise_os_error(*_args, **_kwargs):
        raise OSError("missing rtk")

    monkeypatch.setattr(module.subprocess, "run", raise_os_error)

    module._pre_tool_call(tool_name="terminal", args=args)

    assert args["command"] == "ls"
    assert "rtk rewrite unavailable: missing rtk" in capsys.readouterr().err
