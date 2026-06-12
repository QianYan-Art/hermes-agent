from pathlib import Path
import inspect

from gateway.config import Platform
from gateway.run import GatewayRunner


RETAINED_PLATFORM_FILES = {
    "__init__.py",
    "_http_client_limits.py",
    "api_server.py",
    "base.py",
    "helpers.py",
}


def test_only_retained_platform_source_files_remain():
    platforms_dir = Path("gateway/platforms")
    files = {path.name for path in platforms_dir.iterdir() if path.is_file()}
    dirs = {
        path.name
        for path in platforms_dir.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }

    assert files == RETAINED_PLATFORM_FILES
    assert dirs == {"qqbot"}


def test_gateway_factory_only_instantiates_retained_platforms():
    source = inspect.getsource(GatewayRunner._create_adapter)

    assert "Platform.API_SERVER" in source
    assert "Platform.QQBOT" in source
    for platform in Platform:
        if platform not in {Platform.API_SERVER, Platform.QQBOT}:
            assert f"Platform.{platform.name}" not in source
