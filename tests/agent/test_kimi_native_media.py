"""Kimi Code 主模型的原生媒体能力和请求格式。"""

import base64

import pytest

from agent.image_routing import (
    _lookup_supports_vision,
    build_native_content_parts,
    decide_image_input_mode,
    supports_native_video_input,
)
from agent.transports.chat_completions import ChatCompletionsTransport


@pytest.fixture
def kimi_config(monkeypatch):
    monkeypatch.setattr("agent.models_dev.get_model_capabilities", lambda *_: None)
    return {
        "model": {"provider": "kimi-code", "default": "kimi-for-coding"},
        "providers": {
            "kimi-code": {"base_url": "https://api.kimi.com/coding/v1"},
        },
        "auxiliary": {"vision": {"provider": "auto", "model": "", "base_url": ""}},
    }


@pytest.mark.parametrize(
    "model", ["k3", "k3-256k", "kimi-for-coding", "kimi-for-coding-highspeed"]
)
def test_named_kimi_model_is_native_without_catalog(kimi_config, model):
    assert decide_image_input_mode("custom", model, kimi_config) == "native"


def test_actual_endpoint_wins_over_global_kimi_config(kimi_config):
    assert _lookup_supports_vision(
        "custom", "kimi-for-coding", kimi_config,
        base_url="https://other.example/v1",
    ) is None


@pytest.mark.parametrize("declared", [True, False])
def test_default_vision_override_does_not_leak_to_session_endpoint(kimi_config, declared):
    kimi_config["model"]["supports_vision"] = declared
    assert _lookup_supports_vision(
        "custom", "kimi-for-coding", kimi_config,
        base_url="https://other.example/v1",
    ) is None


def test_named_per_model_override_applies_after_session_model_switch(kimi_config):
    kimi_config["providers"]["kimi-code"]["models"] = {"k3": {"supports_vision": False}}
    assert decide_image_input_mode(
        "custom", "k3", kimi_config, base_url="https://api.kimi.com/coding/v1",
    ) == "text"
    assert _lookup_supports_vision(
        "custom", "other-model", kimi_config,
        base_url="https://api.kimi.com/coding/v1",
    ) is None


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.kimi.com.evil.example/coding/v1",
        "https://api.kimi.com/v1",
        "http://api.kimi.com/coding/v1",
        "https://api.kimi.com:9443/coding/v1",
        "https://api.kimi.com/coding/v1?key=secret",
    ],
)
def test_non_official_endpoint_does_not_enable_native(kimi_config, endpoint):
    kimi_config["providers"]["kimi-code"]["base_url"] = endpoint
    assert decide_image_input_mode("custom", "kimi-for-coding", kimi_config) == "text"


def test_explicit_false_still_wins_for_kimi(kimi_config):
    kimi_config["model"]["supports_vision"] = False
    assert decide_image_input_mode("custom", "kimi-for-coding", kimi_config) == "text"


def test_explicit_auxiliary_backend_is_still_respected(kimi_config):
    kimi_config["auxiliary"]["vision"] = {"provider": "custom:dedicated-vision"}
    assert decide_image_input_mode("custom", "kimi-for-coding", kimi_config) == "text"


def test_agent_keeps_kimi_pixels_with_actual_endpoint(kimi_config, monkeypatch):
    from run_agent import AIAgent

    monkeypatch.setattr("hermes_cli.config.load_config", lambda: kimi_config)
    agent = object.__new__(AIAgent)
    agent.provider = "custom"
    agent.model = "kimi-for-coding"
    agent.base_url = "https://api.kimi.com/coding/v1"
    assert agent._model_supports_vision() is True
    agent.base_url = "https://other.example/v1"
    assert agent._model_supports_vision() is False


def test_mixed_image_video_survives_chat_transport(tmp_path):
    image = tmp_path / "sample.png"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBg"
        "AAAABQABpfZFQAAAAABJRU5ErkJggg=="
    ))
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    content, skipped = build_native_content_parts(
        "描述附件", [str(image)], video_paths=[str(video)],
    )
    assert skipped == []
    message = {"role": "user", "content": content, "_internal": True}
    result = ChatCompletionsTransport().convert_messages(
        [message], model="kimi-for-coding",
    )
    assert [part["type"] for part in result[0]["content"]] == [
        "text", "image_url", "video_url",
    ]
    assert result[0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert result[0]["content"][2]["video_url"]["url"].startswith(
        "data:video/mp4;base64,"
    )
    assert "_internal" not in result[0]
    assert message["_internal"] is True


def test_k3_256k_accepts_images_but_not_video(kimi_config):
    assert decide_image_input_mode("custom", "k3-256k", kimi_config) == "native"
    assert not supports_native_video_input(
        "custom", "k3-256k", "https://api.kimi.com/coding/v1",
    )


def test_official_international_endpoint(kimi_config):
    endpoint = "https://api.kimi.ai/coding/v1"
    assert decide_image_input_mode(
        "custom", "kimi-for-coding", kimi_config, base_url=endpoint,
    ) == "native"
    assert supports_native_video_input("custom", "kimi-for-coding", endpoint)
