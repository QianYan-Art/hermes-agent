import importlib
import subprocess
import sys
from pathlib import Path


def test_tangyuge_bundled_provider_registry_is_narrow():
    for name in list(sys.modules):
        if name.startswith("plugins.model_providers."):
            sys.modules.pop(name, None)

    providers = importlib.reload(importlib.import_module("providers"))

    assert {p.name for p in providers.list_providers()} == {
        "custom",
        "deepseek",
        "minimax",
        "minimax-cn",
        "minimax-oauth",
    }


def test_tangyuge_bundled_plugin_list_is_narrow(tmp_path, monkeypatch):
    from hermes_cli import plugins_cmd

    monkeypatch.setattr(plugins_cmd, "get_hermes_home", lambda: tmp_path)

    names = {entry[0] for entry in plugins_cmd._discover_all_plugins()}

    assert names == {"disk-cleanup", "rtk-rewrite", "security-guidance"}


def test_tangyuge_tracked_provider_plugin_dirs_are_narrow():
    root = Path(__file__).resolve().parents[2]

    model_dirs = {
        path.name
        for path in (root / "plugins" / "model-providers").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    image_dirs = {
        path.name
        for path in (root / "plugins" / "image_gen").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }

    assert model_dirs == {"custom", "deepseek", "minimax"}
    assert image_dirs == {"openai"}


def test_tangyuge_openai_image_backend_autoloads_under_trim_allowlist():
    from agent import image_gen_registry
    from hermes_cli.plugins import PluginManager

    image_gen_registry._reset_for_tests()
    try:
        mgr = PluginManager()
        mgr.discover_and_load()

        loaded = mgr._plugins.get("image_gen/openai")
        assert loaded is not None
        assert loaded.manifest.kind == "backend"
        assert loaded.enabled is True, loaded.error
        assert image_gen_registry.get_provider("openai") is not None
    finally:
        image_gen_registry._reset_for_tests()


def test_tangyuge_removed_cli_command_fails_closed():
    result = subprocess.run(
        [sys.executable, "-m", "hermes_cli.main", "proxy"],
        cwd=".",
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "not retained in Tangyuge-Hermes" in result.stderr
