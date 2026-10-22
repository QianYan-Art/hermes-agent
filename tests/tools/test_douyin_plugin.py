"""抖音插件权限、媒体和协议边界。"""

import asyncio
import base64
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("douyin_plugin_test", ROOT / "ops/douyin-plugin/__init__.py")
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)


@pytest.mark.parametrize("platform,user,chat,owner,allowed", [
    ("qqbot", "owner", "owner", "owner", True),
    ("qqbot", "owner", "group", "owner", False),
    ("qqbot", "other", "owner", "owner", False),
    ("telegram", "owner", "owner", "owner", False),
    ("qqbot", "owner", "owner", "", False),
    ("", "", "", "", True),
])
def test_origin_permission(monkeypatch, platform, user, chat, owner, allowed):
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv("DOUYIN_OWNER_QQ_USER_ID", owner)
    tokens = set_session_vars(platform=platform, user_id=user, chat_id=chat, session_key=f"agent:main:{platform}:dm:{chat}" if platform else "")
    try:
        assert plugin._authorized() is allowed
    finally:
        clear_session_vars(tokens)


def test_group_key_rejected_even_when_ids_equal(monkeypatch):
    from gateway.session_context import clear_session_vars, set_session_vars

    monkeypatch.setenv("DOUYIN_OWNER_QQ_USER_ID", "owner")
    tokens = set_session_vars(platform="qqbot", user_id="owner", chat_id="owner", session_key="agent:main:qqbot:group:owner:owner")
    try:
        assert not plugin._authorized()
    finally:
        clear_session_vars(tokens)


@pytest.mark.parametrize("args", [{}, {"action": "publish"}, {"action": []}, {"action": "login", "url": "https://example.org"}, None])
def test_rejects_arbitrary_operations(args):
    result = json.loads(asyncio.run(plugin.handle(args)))
    assert result["ok"] is False


def test_qr_is_private_file_not_model_base64(tmp_path, monkeypatch):
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(plugin, "_authorized", lambda: True)

    async def response(action):
        return {"ok": True, "state": "login_required", "message": "扫码", "qr_png_base64": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}

    monkeypatch.setattr(plugin, "_request", response)
    output = json.loads(asyncio.run(plugin.handle({"action": "login"})))
    path = Path(output["media_tag"].removeprefix("MEDIA:"))
    assert path.is_file()
    assert path.parent == tmp_path / "cache/douyin-login"
    assert "qr_png_base64" not in output


def test_service_failure_does_not_expose_exception(monkeypatch):
    monkeypatch.setattr(plugin, "_authorized", lambda: True)

    async def response(action):
        raise OSError("secret-test-token")

    monkeypatch.setattr(plugin, "_request", response)
    output = asyncio.run(plugin.handle({"action": "status"}))
    assert json.loads(output)["state"] == "unavailable"
    assert "secret-test-token" not in output


@pytest.mark.parametrize("data", ["not base64", base64.b64encode(b"not png").decode(), None])
def test_invalid_qr_rejected(data):
    with pytest.raises(ValueError):
        plugin._save_qr(data)


def test_registration_uses_standalone_toolset():
    captured = {}
    plugin.register(SimpleNamespace(register_tool=lambda **kw: captured.update(kw)))
    assert captured["name"] == "douyin_login"
    assert captured["toolset"] == "douyin"
    assert captured["is_async"] is True
    assert captured["schema"]["parameters"]["additionalProperties"] is False


def test_explicit_qq_toolset_is_preserved():
    from hermes_cli.tools_config import _get_platform_tools

    enabled = _get_platform_tools({"platform_toolsets": {"qqbot": ["terminal", "douyin"]}}, "qqbot")
    assert "douyin" in enabled
    assert "terminal" in enabled


def test_installed_user_plugin_discovery(tmp_path, monkeypatch):
    import shutil
    import yaml
    from hermes_cli.plugins import PluginManager
    from tools.registry import registry

    home = tmp_path / "home"
    shutil.copytree(ROOT / "ops/douyin-plugin", home / "plugins/douyin-login", ignore=shutil.ignore_patterns("__pycache__"))
    (home / "config.yaml").write_text(yaml.safe_dump({"plugins": {"enabled": ["douyin-login"]}}), encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    try:
        manager = PluginManager()
        manager.discover_and_load()
        assert "douyin_login" in registry._tools
        assert registry._tools["douyin_login"].toolset == "douyin"
    finally:
        registry.deregister("douyin_login")
