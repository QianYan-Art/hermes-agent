"""QQ 语音的缓存归属与回收。

与视频那一处同源的问题：``_convert_audio_to_wav()`` 把转换结果交给
``cache_document_from_bytes``，语音因此落在文档缓存里，和普通文件上传混在
一起；``audio_cache/`` 目录一直存在却没有任何 QQ 路径写入，也没有清理函数。
"""

import os
import time

import pytest


def _make_qq_adapter():
    from gateway.config import PlatformConfig
    from gateway.platforms.qqbot.adapter import QQAdapter

    return QQAdapter(
        PlatformConfig(enabled=True, extra={"app_id": "a", "client_secret": "b"})
    )


@pytest.fixture
def cache_dirs(monkeypatch, tmp_path):
    import gateway.platforms.base as base

    audio = tmp_path / "audio"
    doc = tmp_path / "documents"
    audio.mkdir()
    doc.mkdir()
    monkeypatch.setattr(base, "AUDIO_CACHE_DIR", audio)
    monkeypatch.setattr(base, "DOCUMENT_CACHE_DIR", doc)
    return audio, doc


class TestVoiceCacheSeparation:
    @pytest.mark.asyncio
    async def test_converted_voice_lands_in_audio_cache(self, cache_dirs, monkeypatch):
        audio, doc = cache_dirs
        adapter = _make_qq_adapter()

        async def fake_silk(src, wav):
            from pathlib import Path
            Path(wav).write_bytes(b"RIFF....WAVEfmt ")
            return wav

        monkeypatch.setattr(adapter, "_convert_silk_to_wav", fake_silk)

        path = await adapter._convert_audio_to_wav(b"#!SILK_V3abc", "https://x.example/v.silk")

        assert path is not None
        assert os.path.dirname(path) == str(audio), "语音必须落在音频缓存目录"
        assert path.endswith(".wav")
        assert list(doc.iterdir()) == [], "语音不得写入文档缓存"

    @pytest.mark.asyncio
    async def test_failed_conversion_still_uses_audio_cache(self, cache_dirs, monkeypatch):
        """转换失败的回退路径也要留在音频缓存，否则清理周期会不一致。"""
        audio, doc = cache_dirs
        adapter = _make_qq_adapter()

        async def fail(src, wav):
            return None

        monkeypatch.setattr(adapter, "_convert_silk_to_wav", fail)
        monkeypatch.setattr(adapter, "_convert_ffmpeg_to_wav", fail)

        path = await adapter._convert_audio_to_wav(b"#!SILK_V3abc", "https://x.example/v.silk")

        assert path is not None
        assert os.path.dirname(path) == str(audio)
        assert path.endswith(".silk")
        assert list(doc.iterdir()) == []

    @pytest.mark.asyncio
    async def test_exception_path_uses_audio_cache(self, cache_dirs, monkeypatch):
        audio, doc = cache_dirs
        adapter = _make_qq_adapter()

        async def boom(src, wav):
            raise RuntimeError("converter exploded")

        monkeypatch.setattr(adapter, "_convert_silk_to_wav", boom)

        path = await adapter._convert_audio_to_wav(b"#!SILK_V3abc", "https://x.example/v.silk")

        assert path is not None
        assert os.path.dirname(path) == str(audio)
        assert list(doc.iterdir()) == []


class TestAudioCacheCleanup:
    def test_prunes_only_stale_files(self, cache_dirs):
        import gateway.platforms.base as base

        audio, _ = cache_dirs
        fresh = audio / "audio_fresh.wav"
        stale = audio / "audio_stale.wav"
        fresh.write_bytes(b"a")
        stale.write_bytes(b"b")
        old = time.time() - 48 * 3600
        os.utime(stale, (old, old))

        removed = base.cleanup_audio_cache(max_age_hours=24)

        assert removed == 1
        assert fresh.exists()
        assert not stale.exists()


class TestEveryMediaKindHasCleanup:
    """四类入站媒体各有独立缓存目录和对应的清理函数。"""

    def test_all_four_cleanups_exist_and_are_wired(self):
        import inspect

        import gateway.platforms.base as base
        import gateway.run as run

        for name in (
            "cleanup_image_cache",
            "cleanup_audio_cache",
            "cleanup_video_cache",
            "cleanup_document_cache",
        ):
            assert callable(getattr(base, name, None)), f"{name} 未定义"

        # 四个清理都必须挂在 cron ticker 上，否则定义了也不会被调用。
        ticker_src = inspect.getsource(run._start_cron_ticker)
        for name in (
            "cleanup_image_cache",
            "cleanup_audio_cache",
            "cleanup_video_cache",
            "cleanup_document_cache",
        ):
            assert name in ticker_src, f"{name} 未挂到 cron 清理"

    def test_four_cache_dirs_are_distinct(self):
        import gateway.platforms.base as base

        dirs = {
            "image": base.IMAGE_CACHE_DIR,
            "audio": base.AUDIO_CACHE_DIR,
            "video": base.VIDEO_CACHE_DIR,
            "document": base.DOCUMENT_CACHE_DIR,
        }
        assert len(set(dirs.values())) == 4, f"缓存目录有重叠: {dirs}"
