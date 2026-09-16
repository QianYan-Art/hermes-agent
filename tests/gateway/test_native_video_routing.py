"""内联视频输入的能力判定与 QQ 视频缓存归属。

两个此前的缺口：

1. ``_supports_native_video_input()`` 把"能接受原生视频"写死成 MiniMax M3，
   所以默认模型换成 Kimi Code 之后，即便 Kimi 支持视频理解，QQ 视频也只会
   以缓存路径的文本标记出现。
2. QQ 侧的 ``_download_and_cache()`` 把除图片和语音以外的一切都交给
   ``cache_document_from_bytes``，视频因此落在文档缓存里，既无法与普通文件
   上传区分，也跟着文档的清理节奏被扫掉。
"""

import mimetypes
import os
import time

import pytest

from agent.image_routing import supports_native_video_input


# ---------------------------------------------------------------------------
# 能力表
# ---------------------------------------------------------------------------

class TestSupportsNativeVideoInput:
    def test_minimax_m3_unchanged(self):
        """MiniMax 的 Anthropic 原生 video block 路径保持原行为。"""
        assert supports_native_video_input("minimax-cn", "minimax-m3", "")
        assert supports_native_video_input("minimax", "minimax-m3-preview", "")

    def test_kimi_code_named_provider(self):
        """配置里的 provider slug 是 kimi-code。"""
        assert supports_native_video_input(
            "kimi-code", "kimi-for-coding", "https://api.kimi.com/coding/v1"
        )

    def test_kimi_code_resolved_as_custom(self):
        """命名自定义 provider 在运行时解析成 custom，仍须命中。"""
        assert supports_native_video_input(
            "custom", "kimi-for-coding", "https://api.kimi.com/coding"
        )

    def test_k3_supported(self):
        assert supports_native_video_input(
            "custom", "k3", "https://api.kimi.com/coding/v1"
        )

    def test_k3_256k_not_supported(self):
        """官方模型对比表里 k3-256k 是唯一不支持视频的变体。"""
        assert not supports_native_video_input(
            "custom", "k3-256k", "https://api.kimi.com/coding/v1"
        )

    def test_lookalike_host_rejected(self):
        assert not supports_native_video_input(
            "custom", "kimi-for-coding", "https://api.kimi.com.evil.example/coding/v1"
        )

    def test_wrong_path_rejected(self):
        assert not supports_native_video_input(
            "custom", "kimi-for-coding", "https://api.kimi.com/v1"
        )

    def test_missing_base_url_rejected(self):
        """没有端点信息时不能凭模型名就认定支持。"""
        assert not supports_native_video_input("custom", "kimi-for-coding", "")

    def test_other_provider_rejected(self):
        assert not supports_native_video_input("deepseek", "deepseek-chat", "")


# ---------------------------------------------------------------------------
# base_url 读取
# ---------------------------------------------------------------------------

class TestReadMainBaseUrl:
    def test_runtime_override_wins(self, monkeypatch):
        import agent.auxiliary_client as aux

        monkeypatch.setattr(aux, "_RUNTIME_MAIN_BASE_URL", "https://runtime.example/v1")
        assert aux._read_main_base_url() == "https://runtime.example/v1"

    def test_falls_back_to_named_provider_entry(self, monkeypatch):
        """model.base_url 为空时，从 providers.<slug>.base_url 取。"""
        import agent.auxiliary_client as aux

        monkeypatch.setattr(aux, "_RUNTIME_MAIN_BASE_URL", "")
        monkeypatch.setattr(
            "hermes_cli.config.load_config",
            lambda: {
                "model": {"provider": "kimi-code", "default": "kimi-for-coding"},
                "providers": {
                    "kimi-code": {"base_url": "https://api.kimi.com/coding/v1"}
                },
            },
        )
        assert aux._read_main_base_url() == "https://api.kimi.com/coding/v1"

    def test_model_base_url_preferred_over_provider_entry(self, monkeypatch):
        import agent.auxiliary_client as aux

        monkeypatch.setattr(aux, "_RUNTIME_MAIN_BASE_URL", "")
        monkeypatch.setattr(
            "hermes_cli.config.load_config",
            lambda: {
                "model": {"provider": "kimi-code", "base_url": "https://explicit.example/v1"},
                "providers": {"kimi-code": {"base_url": "https://api.kimi.com/coding/v1"}},
            },
        )
        assert aux._read_main_base_url() == "https://explicit.example/v1"

    def test_returns_empty_when_unconfigured(self, monkeypatch):
        import agent.auxiliary_client as aux

        monkeypatch.setattr(aux, "_RUNTIME_MAIN_BASE_URL", "")
        monkeypatch.setattr(
            "hermes_cli.config.load_config",
            lambda: {"model": {"provider": "minimax-cn", "default": "minimax-m3"}},
        )
        assert aux._read_main_base_url() == ""


# ---------------------------------------------------------------------------
# QQ 视频缓存归属
# ---------------------------------------------------------------------------

def _make_qq_adapter():
    from gateway.config import PlatformConfig
    from gateway.platforms.qqbot.adapter import QQAdapter

    return QQAdapter(
        PlatformConfig(enabled=True, extra={"app_id": "a", "client_secret": "b"})
    )


class _FakeResp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class _FakeHTTP:
    def __init__(self, content: bytes):
        self._content = content

    async def get(self, url, timeout=None, headers=None):
        return _FakeResp(self._content)


class TestQQVideoCacheSeparation:
    @pytest.mark.asyncio
    async def test_video_lands_in_video_cache(self, monkeypatch, tmp_path):
        """video/* 附件应进入视频缓存，而不是文档缓存。"""
        import gateway.platforms.base as base

        video_dir = tmp_path / "videos"
        doc_dir = tmp_path / "documents"
        video_dir.mkdir()
        doc_dir.mkdir()
        monkeypatch.setattr(base, "VIDEO_CACHE_DIR", video_dir)
        monkeypatch.setattr(base, "DOCUMENT_CACHE_DIR", doc_dir)

        adapter = _make_qq_adapter()
        adapter._http_client = _FakeHTTP(b"\x00\x00\x00\x18ftypmp42")

        path = await adapter._download_and_cache(
            "https://multimedia.nt.qq.com.cn/download/v1",
            "video/mp4",
            "clip.mp4",
        )

        assert path is not None
        assert os.path.dirname(path) == str(video_dir), "视频必须落在视频缓存目录"
        assert list(doc_dir.iterdir()) == [], "视频不得写入文档缓存"
        assert path.endswith(".mp4")

    @pytest.mark.asyncio
    async def test_plain_file_upload_stays_document(self, monkeypatch, tmp_path):
        """QQ 普通文件上传标记为 file，即使扩展名像视频也按文件交付。"""
        import gateway.platforms.base as base

        video_dir = tmp_path / "videos"
        doc_dir = tmp_path / "documents"
        video_dir.mkdir()
        doc_dir.mkdir()
        monkeypatch.setattr(base, "VIDEO_CACHE_DIR", video_dir)
        monkeypatch.setattr(base, "DOCUMENT_CACHE_DIR", doc_dir)

        adapter = _make_qq_adapter()
        adapter._http_client = _FakeHTTP(b"\x00\x00\x00\x18ftypmp42")

        path = await adapter._download_and_cache(
            "https://multimedia.nt.qq.com.cn/download/f1",
            "file",
            "clip.mp4",
        )

        assert path is not None
        assert os.path.dirname(path) == str(doc_dir)
        assert list(video_dir.iterdir()) == []

    def test_video_ext_prefers_real_container(self):
        from gateway.platforms.qqbot.adapter import QQAdapter

        pick = QQAdapter._video_ext_for
        assert pick("video/quicktime", "clip.mov", "") == ".mov"
        assert pick("video/mp4", "", "https://x.example/a/b/clip.webm") == ".webm"
        assert pick("video/mp4", "noext", "https://x.example/noext") == ".mp4"
        # 不认识的容器不要伪造成 SUPPORTED_VIDEO_TYPES 之外的后缀
        assert pick("video/ogg", "clip.ogv", "") in {".mp4", mimetypes.guess_extension("video/ogg")}


class TestVideoCacheCleanup:
    def test_prunes_only_stale_files(self, monkeypatch, tmp_path):
        import gateway.platforms.base as base

        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        monkeypatch.setattr(base, "VIDEO_CACHE_DIR", video_dir)

        fresh = video_dir / "video_fresh.mp4"
        stale = video_dir / "video_stale.mp4"
        fresh.write_bytes(b"a")
        stale.write_bytes(b"b")
        old = time.time() - 48 * 3600
        os.utime(stale, (old, old))

        removed = base.cleanup_video_cache(max_age_hours=24)

        assert removed == 1
        assert fresh.exists()
        assert not stale.exists()
