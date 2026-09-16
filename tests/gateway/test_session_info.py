"""Tests for GatewayRunner._format_session_info — session config surfacing."""

import pytest
from unittest.mock import patch

from gateway.run import GatewayRunner


@pytest.fixture()
def runner():
    """Create a bare GatewayRunner without __init__."""
    return GatewayRunner.__new__(GatewayRunner)


def _patch_info(tmp_path, config_yaml, model, runtime):
    """Return a context-manager stack that patches _format_session_info deps."""
    cfg_path = tmp_path / "config.yaml"
    if config_yaml is not None:
        cfg_path.write_text(config_yaml)
    return (
        patch("gateway.run._hermes_home", tmp_path),
        patch("gateway.run._resolve_gateway_model", return_value=model),
        patch("gateway.run._resolve_runtime_agent_kwargs", return_value=runtime),
    )


class TestFormatSessionInfo:

    def test_includes_model_name(self, runner, tmp_path):
        p1, p2, p3 = _patch_info(tmp_path, "model:\n  default: anthropic/claude-opus-4.6\n  provider: openrouter\n",
                                  "anthropic/claude-opus-4.6",
                                  {"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1", "api_key": "k"})
        with p1, p2, p3:
            info = runner._format_session_info()
        assert "claude-opus-4.6" in info

    def test_includes_provider(self, runner, tmp_path):
        p1, p2, p3 = _patch_info(tmp_path, "model:\n  default: test-model\n  provider: openrouter\n",
                                  "test-model",
                                  {"provider": "openrouter", "base_url": "", "api_key": ""})
        with p1, p2, p3:
            info = runner._format_session_info()
        assert "openrouter" in info

    def test_config_context_length(self, runner, tmp_path):
        p1, p2, p3 = _patch_info(tmp_path, "model:\n  default: test-model\n  context_length: 32768\n",
                                  "test-model",
                                  {"provider": "custom", "base_url": "", "api_key": ""})
        with p1, p2, p3:
            info = runner._format_session_info()
        assert "32K" in info
        assert "config" in info

    def test_default_fallback_hint(self, runner, tmp_path):
        p1, p2, p3 = _patch_info(tmp_path, "model:\n  default: unknown-model-xyz\n",
                                  "unknown-model-xyz",
                                  {"provider": "", "base_url": "", "api_key": ""})
        with p1, p2, p3:
            info = runner._format_session_info()
        assert "250K (256,000 tokens;" in info
        assert "model.context_length" in info

    def test_local_endpoint_shown(self, runner, tmp_path):
        p1, p2, p3 = _patch_info(
            tmp_path,
            "model:\n  default: qwen3:8b\n  provider: custom\n  base_url: http://localhost:11434/v1\n  context_length: 8192\n",
            "qwen3:8b",
            {"provider": "custom", "base_url": "http://localhost:11434/v1", "api_key": ""})
        with p1, p2, p3:
            info = runner._format_session_info()
        assert "localhost:11434" in info
        assert "8K" in info

    def test_cloud_endpoint_hidden(self, runner, tmp_path):
        p1, p2, p3 = _patch_info(tmp_path, "model:\n  default: test-model\n  provider: openrouter\n",
                                  "test-model",
                                  {"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1", "api_key": "k"})
        with p1, p2, p3:
            info = runner._format_session_info()
        assert "Endpoint" not in info

    def test_million_context_format(self, runner, tmp_path):
        p1, p2, p3 = _patch_info(tmp_path, "model:\n  default: test-model\n  context_length: 1000000\n",
                                  "test-model",
                                  {"provider": "", "base_url": "", "api_key": ""})
        with p1, p2, p3:
            info = runner._format_session_info()
        assert "Context: 1,000,000 tokens (config)" in info

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (512, "512 tokens (config)"),
            (1023, "1,023 tokens (config)"),
            (1024, "1K (1,024 tokens; config)"),
            (1025, "1,025 tokens (config)"),
            (262144, "256K (262,144 tokens; config)"),
            (524288, "512K (524,288 tokens; config)"),
            (1048575, "1,048,575 tokens (config)"),
            (1048576, "1M (1,048,576 tokens; config)"),
            (1048577, "1,048,577 tokens (config)"),
            (1572864, "1536K (1,572,864 tokens; config)"),
            (512000, "500K (512,000 tokens; config)"),
            (1000000, "1,000,000 tokens (config)"),
        ],
    )
    def test_context_uses_exact_binary_units_without_rounding(self, runner, tmp_path, value, expected):
        """会话边界回显只在整倍数时缩写，避免浮点四舍五入跨边界。"""
        p1, p2, p3 = _patch_info(
            tmp_path,
            f"model:\n  default: test-model\n  context_length: {value}\n",
            "test-model",
            {"provider": "custom", "base_url": "", "api_key": ""},
        )
        with p1, p2, p3:
            info = runner._format_session_info()
        assert f"Context: {expected}" in info

    def test_session_override_info_uses_session_model_provider_and_context(self, runner, tmp_path):
        runner._session_model_overrides = {
            "session-1": {
                "model": "session-model",
                "provider": "session-provider",
                "base_url": "http://localhost:1234/v1",
                "api_key": "session-key",
                "context_length": 131072,
            }
        }
        p1, p2, p3 = _patch_info(
            tmp_path,
            "model:\n  default: global-model\n  provider: global-provider\n  context_length: 262144\n",
            "global-model",
            {"provider": "global-provider", "base_url": "", "api_key": "global-key"},
        )
        with p1, p2, p3:
            info = runner._format_session_info("session-1")

        assert "Model: `session-model`" in info
        assert "Provider: session-provider" in info
        assert "Context: 128K (131,072 tokens; session override)" in info
        assert "Endpoint: http://localhost:1234/v1" in info

    def test_missing_config(self, runner, tmp_path):
        """No config.yaml should not crash."""
        p1, p2, p3 = _patch_info(tmp_path, None,  # don't create config
                                  "anthropic/claude-sonnet-4.6",
                                  {"provider": "openrouter", "base_url": "", "api_key": ""})
        with p1, p2, p3:
            info = runner._format_session_info()
        assert "Model" in info
        assert "Context" in info

    def test_runtime_resolution_failure_doesnt_crash(self, runner, tmp_path):
        """If runtime resolution raises, should still produce output."""
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("model:\n  default: test-model\n  context_length: 4096\n")
        with patch("gateway.run._hermes_home", tmp_path), \
             patch("gateway.run._resolve_gateway_model", return_value="test-model"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", side_effect=RuntimeError("no creds")):
            info = runner._format_session_info()
        assert "4K" in info
        assert "config" in info
