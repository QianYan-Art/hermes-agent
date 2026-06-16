import importlib
import subprocess
import sys


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
