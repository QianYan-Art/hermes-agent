from __future__ import annotations

import json
import pytest

from agent import image_gen_registry
from agent.image_gen_provider import ImageGenProvider


@pytest.fixture(autouse=True)
def _reset_registry():
    image_gen_registry._reset_for_tests()
    yield
    image_gen_registry._reset_for_tests()


class _FakeCodexProvider(ImageGenProvider):
    @property
    def name(self) -> str:
        return "codex"

    def generate(self, prompt, aspect_ratio="landscape", **kwargs):
        return {
            "success": True,
            "image": "/tmp/codex-test.png",
            "model": "gpt-5.2-codex",
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "provider": "codex",
            "kwargs": kwargs,
        }


class _UnavailableCodexProvider(_FakeCodexProvider):
    def is_available(self) -> bool:
        return False


class TestPluginDispatch:
    def test_requirements_keep_configured_provider_visible(self, monkeypatch):
        import model_tools
        from tools import image_generation_tool
        from tools.registry import invalidate_check_fn_cache
        from agent import image_gen_registry as registry_module
        from hermes_cli import plugins as plugins_module

        provider = _UnavailableCodexProvider()

        monkeypatch.setattr(image_generation_tool, "check_fal_api_key", lambda: False)
        monkeypatch.setattr(
            image_generation_tool,
            "_read_configured_image_provider",
            lambda: "codex",
        )
        monkeypatch.setattr(
            plugins_module,
            "_ensure_plugins_discovered",
            lambda force=False: None,
        )
        monkeypatch.setattr(
            registry_module,
            "get_provider",
            lambda name: provider if name == "codex" else None,
        )
        monkeypatch.setattr(registry_module, "list_providers", lambda: [provider])

        invalidate_check_fn_cache()
        model_tools._clear_tool_defs_cache()

        assert image_generation_tool.check_image_generation_requirements() is True

        definitions = model_tools.get_tool_definitions(
            enabled_toolsets=["image_gen"],
            quiet_mode=True,
        )
        assert [d["function"]["name"] for d in definitions] == ["image_generate"]
        properties = definitions[0]["function"]["parameters"]["properties"]
        assert "input_image" in properties
        assert "input_images" in properties
        assert "mask" in properties
        assert "api_model" in properties

    def test_requirements_hide_unconfigured_unavailable_provider(self, monkeypatch):
        from tools import image_generation_tool
        from tools.registry import invalidate_check_fn_cache
        from agent import image_gen_registry as registry_module
        from hermes_cli import plugins as plugins_module

        provider = _UnavailableCodexProvider()

        monkeypatch.setattr(image_generation_tool, "check_fal_api_key", lambda: False)
        monkeypatch.setattr(
            image_generation_tool,
            "_read_configured_image_provider",
            lambda: None,
        )
        monkeypatch.setattr(
            plugins_module,
            "_ensure_plugins_discovered",
            lambda force=False: None,
        )
        monkeypatch.setattr(registry_module, "list_providers", lambda: [provider])

        invalidate_check_fn_cache()

        assert image_generation_tool.check_image_generation_requirements() is False

    def test_dispatch_routes_to_codex_provider(self, monkeypatch, tmp_path):
        from tools import image_generation_tool
        from agent import image_gen_registry as registry_module
        from hermes_cli import plugins as plugins_module

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "config.yaml").write_text("image_gen:\n  provider: codex\n")
        image_gen_registry.register_provider(_FakeCodexProvider())

        monkeypatch.setattr(image_generation_tool, "_read_configured_image_provider", lambda: "codex")
        monkeypatch.setattr(plugins_module, "_ensure_plugins_discovered", lambda: None)
        monkeypatch.setattr(registry_module, "get_provider", lambda name: _FakeCodexProvider() if name == "codex" else None)

        dispatched = image_generation_tool._dispatch_to_plugin_provider("draw cat", "square")
        payload = json.loads(dispatched)

        assert payload["success"] is True
        assert payload["provider"] == "codex"
        assert payload["image"] == "/tmp/codex-test.png"
        assert payload["aspect_ratio"] == "square"

    def test_dispatch_forwards_image_generation_options(self, monkeypatch, tmp_path):
        from tools import image_generation_tool
        from hermes_cli import plugins as plugins_module
        from agent import image_gen_registry as registry_module

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "config.yaml").write_text("image_gen:\n  provider: codex\n")

        monkeypatch.setattr(image_generation_tool, "_read_configured_image_provider", lambda: "codex")
        monkeypatch.setattr(image_generation_tool, "_read_configured_image_model", lambda: None)
        monkeypatch.setattr(plugins_module, "_ensure_plugins_discovered", lambda: None)
        monkeypatch.setattr(registry_module, "get_provider", lambda name: _FakeCodexProvider() if name == "codex" else None)

        dispatched = image_generation_tool._dispatch_to_plugin_provider(
            "draw cat",
            "square",
            {
                "quality": "high",
                "num_images": 2,
                "output_format": "png",
                "background": "transparent",
                "moderation": "low",
                "output_compression": 80,
                "style": "natural",
                "input_image": "/tmp/source.png",
                "mask": "/tmp/mask.png",
                "input_fidelity": "high",
                "api_model": "custom-image-model",
            },
        )
        payload = json.loads(dispatched)

        assert payload["success"] is True
        assert payload["kwargs"] == {
            "quality": "high",
            "num_images": 2,
            "output_format": "png",
            "background": "transparent",
            "moderation": "low",
            "output_compression": 80,
            "style": "natural",
            "input_image": "/tmp/source.png",
            "mask": "/tmp/mask.png",
            "input_fidelity": "high",
            "api_model": "custom-image-model",
        }

    def test_dispatch_reports_missing_registered_provider(self, monkeypatch, tmp_path):
        from tools import image_generation_tool
        from hermes_cli import plugins as plugins_module

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "config.yaml").write_text("image_gen:\n  provider: missing-codex\n")

        monkeypatch.setattr(image_generation_tool, "_read_configured_image_provider", lambda: "missing-codex")
        monkeypatch.setattr(plugins_module, "_ensure_plugins_discovered", lambda: None)

        dispatched = image_generation_tool._dispatch_to_plugin_provider("draw cat", "landscape")
        payload = json.loads(dispatched)

        assert payload["success"] is False
        assert payload["error_type"] == "provider_not_registered"
        assert "image_gen.provider='missing-codex'" in payload["error"]

    def test_dispatch_force_refreshes_plugins_when_provider_initially_missing(self, monkeypatch, tmp_path):
        from tools import image_generation_tool
        from hermes_cli import plugins as plugins_module
        from agent import image_gen_registry as registry_module

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "config.yaml").write_text("image_gen:\n  provider: codex\n")

        monkeypatch.setattr(image_generation_tool, "_read_configured_image_provider", lambda: "codex")

        calls = []
        provider_state = {"provider": None}

        def fake_ensure_plugins_discovered(force=False):
            calls.append(force)
            if force:
                provider_state["provider"] = _FakeCodexProvider()

        monkeypatch.setattr(plugins_module, "_ensure_plugins_discovered", fake_ensure_plugins_discovered)
        monkeypatch.setattr(registry_module, "get_provider", lambda name: provider_state["provider"])

        dispatched = image_generation_tool._dispatch_to_plugin_provider("draw hammy", "portrait")
        payload = json.loads(dispatched)

        assert calls == [False, True]
        assert payload["success"] is True
        assert payload["provider"] == "codex"
        assert payload["aspect_ratio"] == "portrait"
