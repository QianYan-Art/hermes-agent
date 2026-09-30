import pytest
import yaml
from unittest.mock import Mock

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource


def _event(text: str) -> MessageEvent:
    return MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.QQBOT,
            user_id="u1",
            chat_id="c1",
            user_name="tester",
            chat_type="dm",
        ),
        message_id="m1",
    )


@pytest.mark.asyncio
async def test_auxmodel_openai_image_auth_uses_default_image_key_env(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "\n".join(
            [
                "image_gen:",
                "  provider: openai",
                "  model: gpt-image-2-medium",
                "  openai:",
                "    base_url: https://suyuan.4071253.xyz/v1",
                "    model: gpt-image-2-medium",
                "    timeout: 180",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("OPENAI_IMAGE_API_KEY", "image-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    result = await runner._handle_auxmodel_command(_event("/auxmodel"))

    assert "image: gpt-image-2-medium" in result
    assert "  provider: openai" in result
    assert "  endpoint: https://suyuan.4071253.xyz/v1" in result
    assert "  auth: OPENAI_IMAGE_API_KEY（已设置）" in result


@pytest.mark.asyncio
async def test_auxmodel_image_can_write_non_tier_api_model(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    config_path = hermes_home / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "image_gen:",
                "  provider: openai",
                "  model: gpt-image-2-medium",
                "  openai:",
                "    base_url: https://suyuan.4071253.xyz/v1",
                "    model: gpt-image-2-medium",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    result = await runner._handle_auxmodel_command(
        _event("/auxmodel image custom-image-model")
    )
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert "新模型: custom-image-model" in result
    assert saved["image_gen"]["model"] == "custom-image-model"
    assert saved["image_gen"]["openai"]["model"] == "custom-image-model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("", "未设置"),
        (", \n ,", "未设置"),
        ("secret-one", "已设置 1 个 key"),
        ("secret-one,\nsecret-two", "轮换 2 个 key，失败依次回退"),
    ],
)
async def test_auxmodel_native_vision_and_tavily_status_are_read_only(tmp_path, monkeypatch, keys, expected):
    from gateway.run import GatewayRunner
    from plugins.web.tavily.provider import TavilyWebSearchProvider
    import agent.web_search_registry as registry

    cfg = {
        "model": {"provider": "kimi-code", "default": "kimi-for-coding"},
        "auxiliary": {"vision": {"provider": "auto", "model": "", "base_url": ""}},
        "web": {"backend": "tavily"},
    }
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: cfg)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TAVILY_API_KEY", keys)
    monkeypatch.delenv("TAVILY_BASE_URL", raising=False)
    monkeypatch.setattr(registry, "_providers", {"tavily": TavilyWebSearchProvider()})
    network = Mock(side_effect=AssertionError("状态查询不能联网"))
    monkeypatch.setattr("httpx.post", network)
    runner = object.__new__(GatewayRunner)
    runner._resolve_session_agent_runtime = lambda **_: (
        "kimi-for-coding",
        {"provider": "custom", "base_url": "https://api.kimi.com/coding/v1"},
    )

    result = await runner._handle_auxmodel_command(_event("/auxmodel"))

    assert "主模型: kimi-for-coding" in result
    assert "图片: 原生直传" in result
    assert "视频: 原生直传" in result
    assert "vision:" not in result
    assert "ollama" not in result.lower()
    assert "联网搜索: tavily" in result
    assert "网页提取: tavily" in result
    assert f"TAVILY_API_KEY（{expected}）" in result
    assert "未联网校验" in result
    assert "secret-one" not in result and "secret-two" not in result
    network.assert_not_called()
    assert not (tmp_path / "config.yaml").exists()


@pytest.mark.asyncio
async def test_auxmodel_tavily_is_not_claimed_active_with_other_backend(monkeypatch, tmp_path):
    from gateway.run import GatewayRunner
    from plugins.web.tavily.provider import TavilyWebSearchProvider
    import agent.web_search_registry as registry

    class OtherProvider(TavilyWebSearchProvider):
        name = "other"

    cfg = {"web": {"search_backend": "other", "extract_backend": "tavily"}}
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: cfg)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TAVILY_API_KEY", "secret")
    monkeypatch.setattr(
        registry, "_providers",
        {"tavily": TavilyWebSearchProvider(), "other": OtherProvider()},
    )
    runner = object.__new__(GatewayRunner)
    result = await runner._handle_auxmodel_command(_event("/auxmodel"))
    assert "联网搜索: other" in result
    assert "网页提取: tavily" in result


@pytest.mark.asyncio
async def test_auxmodel_default_backend_follows_registry(monkeypatch, tmp_path):
    from gateway.run import GatewayRunner
    from plugins.web.tavily.provider import TavilyWebSearchProvider
    import agent.web_search_registry as registry

    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TAVILY_API_KEY", "secret")
    monkeypatch.setattr(registry, "_providers", {"tavily": TavilyWebSearchProvider()})
    runner = object.__new__(GatewayRunner)
    assert "联网搜索: tavily" in await runner._handle_auxmodel_command(_event("/auxmodel"))
    monkeypatch.setenv("TAVILY_API_KEY", ", \n,")
    assert "联网搜索: 无可用后端" in await runner._handle_auxmodel_command(_event("/auxmodel"))


@pytest.mark.asyncio
async def test_auxmodel_vision_does_not_create_aux_override(monkeypatch, tmp_path):
    from gateway.run import GatewayRunner

    cfg = {"model": {"provider": "kimi-code", "default": "kimi-for-coding"}}
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: cfg)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    runner = object.__new__(GatewayRunner)
    result = await runner._handle_auxmodel_command(_event("/auxmodel vision another-model"))
    assert "未修改配置" in result
    assert "auxiliary" not in cfg
    assert not (tmp_path / "config.yaml").exists()


@pytest.mark.asyncio
async def test_auxmodel_does_not_echo_endpoint_credentials(monkeypatch, tmp_path):
    from gateway.run import GatewayRunner

    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {
        "image_gen": {
            "provider": "openai",
            "openai": {"base_url": "https://user:secret-password@image.example/v1?key=secret-query"},
        },
    })
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv(
        "TAVILY_BASE_URL", "https://user:secret-password@search.example/v1?key=secret-query#secret-fragment",
    )
    result = await object.__new__(GatewayRunner)._handle_auxmodel_command(_event("/auxmodel"))
    assert "endpoint: https://search.example/v1" in result
    assert "endpoint: https://image.example/v1" in result
    assert "secret-" not in result
    assert "user:" not in result
