from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest


OPS_DIR = Path(__file__).parents[2] / "ops" / "douyin-login"
if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))

RELEASES_SPEC = importlib.util.spec_from_file_location("releases", OPS_DIR / "releases.py")
assert RELEASES_SPEC is not None and RELEASES_SPEC.loader is not None
releases = importlib.util.module_from_spec(RELEASES_SPEC)
sys.modules[RELEASES_SPEC.name] = releases
RELEASES_SPEC.loader.exec_module(releases)

STAGE_SPEC = importlib.util.spec_from_file_location(
    "douyin_stage_release", OPS_DIR / "stage_release.py"
)
assert STAGE_SPEC is not None and STAGE_SPEC.loader is not None
stage_release = importlib.util.module_from_spec(STAGE_SPEC)
sys.modules[STAGE_SPEC.name] = stage_release
STAGE_SPEC.loader.exec_module(stage_release)


def _manifest(release_id: str, video: bytes, **overrides) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "release_id": release_id,
        "title": "序栞：第一集",
        "description": "已导出并烧录字幕。",
        "ai_generated": True,
        "video_sha256": hashlib.sha256(video).hexdigest(),
        "video_bytes": len(video),
        "duration": 63.25,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "created_at": "2026-10-22T18:30:00Z",
    }
    value.update(overrides)
    return value


def _write_package(directory: Path, release_id: str, video: bytes, **overrides) -> Path:
    package = directory / release_id
    package.mkdir(parents=True)
    (package / "video.mp4").write_bytes(video)
    (package / "manifest.json").write_text(
        json.dumps(_manifest(release_id, video, **overrides), ensure_ascii=False),
        encoding="utf-8",
    )
    return package


def _symlink_or_skip(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"符号链接权限不可用：{exc}")


def test_store_lists_summaries_and_loads_verified_video(tmp_path):
    data_dir = tmp_path / "state"
    release_id = "ep00-xu-kan"
    video = b"small test fixture"
    package = _write_package(data_dir / "releases", release_id, video)
    store = releases.ReleaseStore(data_dir)

    summaries = store.list_releases()
    loaded = store.load(release_id)

    assert [item["release_id"] for item in summaries] == [release_id]
    assert all("video_path" not in item for item in summaries)
    assert loaded["video_path"] == package / "video.mp4"
    assert loaded["video_path"].read_bytes() == video
    assert loaded["video_sha256"] == hashlib.sha256(video).hexdigest()


def test_store_does_not_touch_chromium_profile(tmp_path):
    data_dir = tmp_path / "state"
    profile = data_dir / "chromium-profile"
    profile.mkdir(parents=True)
    marker = profile / "sentinel"
    marker.write_text("unchanged", encoding="utf-8")

    assert releases.ReleaseStore(data_dir).list_releases() == []
    assert marker.read_text(encoding="utf-8") == "unchanged"


@pytest.mark.parametrize("release_id", ["../escape", "Upper", "", "a" * 65, "序栞"])
def test_store_rejects_invalid_release_id(tmp_path, release_id):
    with pytest.raises(releases.ReleaseError):
        releases.ReleaseStore(tmp_path).load(release_id)


def test_store_rejects_video_hash_and_size_mismatch(tmp_path):
    data_dir = tmp_path / "state"
    package = _write_package(data_dir / "releases", "ep00", b"valid bytes")
    (package / "video.mp4").write_bytes(b"other bytes")

    with pytest.raises(releases.ReleaseError, match="hash"):
        releases.ReleaseStore(data_dir).load("ep00")


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "x" * 31),
        ("title", "  "),
        ("title", "标题\n换行"),
        ("title", "标题\r换行"),
        ("title", "标题\0空字符"),
        ("description", "x" * 1001),
        ("description", "简介\0空字符"),
        ("ai_generated", False),
        ("video_sha256", "z" * 64),
        ("video_bytes", True),
        ("duration", float("nan")),
        ("width", 0),
        ("height", -1),
        ("fps", 0),
        ("created_at", "2026-10-22T18:30:00-07:00"),
        ("source", "x" * 201),
        ("cover.jpg", "unsupported"),
    ],
)
def test_manifest_rejects_values_outside_schema(tmp_path, field, value):
    manifest = _manifest("ep00", b"video")
    manifest[field] = value

    with pytest.raises(releases.ReleaseError):
        releases.validate_manifest(manifest)


def test_store_rejects_symlinked_release_directory(tmp_path):
    data_dir = tmp_path / "state"
    releases_dir = data_dir / "releases"
    releases_dir.mkdir(parents=True)
    external = tmp_path / "external"
    _write_package(external, "ep00", b"video")
    _symlink_or_skip(releases_dir / "ep00", external / "ep00", target_is_directory=True)

    with pytest.raises(releases.ReleaseError, match="链接"):
        releases.ReleaseStore(data_dir).load("ep00")


def test_store_rejects_symlinked_data_directory(tmp_path):
    target = tmp_path / "target"
    (target / "releases").mkdir(parents=True)
    _write_package(target / "releases", "ep00", b"video")
    alias = tmp_path / "alias"
    _symlink_or_skip(alias, target, target_is_directory=True)

    with pytest.raises(releases.ReleaseError, match="链接"):
        releases.ReleaseStore(alias).load("ep00")


@pytest.mark.parametrize("filename", ["manifest.json", "video.mp4"])
def test_store_rejects_symlinked_package_files(tmp_path, filename):
    data_dir = tmp_path / "state"
    package = _write_package(data_dir / "releases", "ep00", b"video")
    original = package / filename
    outside = tmp_path / f"outside-{filename}"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    _symlink_or_skip(original, outside)

    with pytest.raises(releases.ReleaseError, match="链接"):
        releases.ReleaseStore(data_dir).load("ep00")


def test_store_rejects_unsupported_cover_file(tmp_path):
    data_dir = tmp_path / "state"
    package = _write_package(data_dir / "releases", "ep00", b"video")
    (package / "cover.jpg").write_bytes(b"cover")

    with pytest.raises(releases.ReleaseError, match="仅包含"):
        releases.ReleaseStore(data_dir).load("ep00")


def test_prepare_writes_manifest_without_copying_original_video(tmp_path, monkeypatch):
    video_path = tmp_path / "export.mp4"
    video = b"already-exported-video"
    video_path.write_bytes(video)
    output_dir = tmp_path / ".mission"
    output_dir.mkdir()
    output = output_dir / "manifest.json"
    monkeypatch.setattr(
        stage_release,
        "probe_video",
        lambda _path: {"duration": 63.25, "width": 1920, "height": 1080, "fps": 30.0},
    )

    result = stage_release.prepare_release(
        video_path,
        "ep00-xu-kan",
        "序栞：第一集",
        "已导出并烧录字幕。",
        output,
        source="OpenFilm export",
    )

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert result == manifest
    assert manifest["video_sha256"] == hashlib.sha256(video).hexdigest()
    assert manifest["video_bytes"] == len(video)
    assert manifest["source"] == "OpenFilm export"
    assert video_path.read_bytes() == video
    assert not (output_dir / "video.mp4").exists()


def test_probe_metadata_requires_h264_aac_and_positive_dimensions():
    valid = {
        "format": {"duration": "12.5"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    assert stage_release._metadata_from_probe(valid)["fps"] == pytest.approx(29.97, rel=1e-3)

    valid["streams"][0]["codec_name"] = "hevc"
    with pytest.raises(releases.ReleaseError, match="H.264"):
        stage_release._metadata_from_probe(valid)


def test_install_is_atomic_private_and_idempotent_for_same_content(tmp_path):
    video = b"same content"
    source = _write_package(tmp_path / "source", "ep00", video)
    data_dir = tmp_path / "state"

    assert stage_release.install_release(source, data_dir) == "ep00"
    installed = releases.ReleaseStore(data_dir).load("ep00")
    assert installed["video_path"].read_bytes() == video

    replacement = _write_package(
        tmp_path / "second-source",
        "ep00",
        video,
        created_at="2026-10-23T02:00:00Z",
    )
    assert stage_release.install_release(replacement, data_dir) == "ep00"

    if os.name == "posix":
        assert stat.S_IMODE((data_dir / "releases").stat().st_mode) == 0o700
        assert stat.S_IMODE((data_dir / "releases" / "ep00").stat().st_mode) == 0o700
        assert stat.S_IMODE(installed["video_path"].stat().st_mode) == 0o600
        assert stat.S_IMODE((data_dir / "releases" / "ep00" / "manifest.json").stat().st_mode) == 0o600


def test_install_rejects_same_id_with_different_content(tmp_path):
    data_dir = tmp_path / "state"
    first = _write_package(tmp_path / "source-a", "ep00", b"video", description="first")
    second = _write_package(tmp_path / "source-b", "ep00", b"video", description="second")
    stage_release.install_release(first, data_dir)

    with pytest.raises(releases.ReleaseError, match="拒绝覆盖"):
        stage_release.install_release(second, data_dir)


def test_install_rejects_invalid_source_before_creating_release(tmp_path):
    source = tmp_path / "source" / "ep00"
    source.mkdir(parents=True)
    (source / "video.mp4").write_bytes(b"video")
    data_dir = tmp_path / "state"

    with pytest.raises(releases.ReleaseError):
        stage_release.install_release(source, data_dir)
    assert not (data_dir / "releases" / "ep00").exists()


def test_install_rejects_symlinked_source_video(tmp_path):
    source = _write_package(tmp_path / "source", "ep00", b"video")
    video_path = source / "video.mp4"
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(video_path.read_bytes())
    video_path.unlink()
    _symlink_or_skip(video_path, outside)

    with pytest.raises(releases.ReleaseError, match="链接"):
        stage_release.install_release(source, tmp_path / "state")

