from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageOps, PngImagePlugin


OPS_DIR = Path(__file__).parents[2] / "ops" / "douyin-login"
if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))

import releases

COVERS_SPEC = importlib.util.spec_from_file_location("douyin_covers", OPS_DIR / "covers.py")
assert COVERS_SPEC is not None and COVERS_SPEC.loader is not None
covers = importlib.util.module_from_spec(COVERS_SPEC)
sys.modules[COVERS_SPEC.name] = covers
COVERS_SPEC.loader.exec_module(covers)


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


def _write_release(data_dir: Path, release_id: str = "ep00", video: bytes = b"original video") -> Path:
    package = data_dir / "releases" / release_id
    package.mkdir(parents=True)
    (package / "video.mp4").write_bytes(video)
    (package / "manifest.json").write_text(
        json.dumps(_manifest(release_id, video), ensure_ascii=False), encoding="utf-8"
    )
    return package / "video.mp4"


def _image_bytes(
    fmt: str = "PNG",
    *,
    color: tuple[int, int, int] = (200, 20, 30),
    size: tuple[int, int] = (80, 60),
    exif_orientation: int | None = None,
    note: str | None = None,
) -> bytes:
    output = io.BytesIO()
    image = Image.new("RGB", size, color)
    options: dict[str, object] = {}
    if exif_orientation is not None:
        exif = Image.Exif()
        exif[274] = exif_orientation
        options["exif"] = exif
    if note is not None and fmt == "PNG":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("note", note)
        options["pnginfo"] = metadata
    image.save(output, format=fmt, **options)
    return output.getvalue()


def _store(tmp_path: Path, *, release_id: str = "ep00", video: bytes = b"original video"):
    data_dir = tmp_path / "state"
    video_path = _write_release(data_dir, release_id, video)
    release_store = releases.ReleaseStore(data_dir)
    return data_dir, video_path, covers.CoverStore(data_dir, release_store)


def test_import_creates_private_oriented_assets_and_safe_public_previews(tmp_path):
    data_dir, _video_path, store = _store(tmp_path)
    uploaded = _image_bytes("JPEG", size=(80, 40), exif_orientation=6)

    public = store.import_image("ep00", uploaded)
    private = store.load("ep00", public["cover_id"])

    assert set(public) == {
        "release_id",
        "cover_id",
        "cover_sha256",
        "video_sha256",
        "source",
        "previews",
    }
    assert public["source"] == "qq_image"
    assert private["source_path"].name == "source.jpg"
    assert private["landscape_path"].name == "landscape.jpg"
    assert private["portrait_path"].name == "portrait.jpg"
    with Image.open(private["source_path"]) as source:
        assert source.size == (40, 80)
        assert not source.getexif()
    with Image.open(private["landscape_path"]) as landscape:
        assert landscape.size == (1200, 900)
        assert max(landscape.getpixel((0, 0))) < 20
        assert landscape.getpixel((600, 450))[0] > 150
    with Image.open(private["portrait_path"]) as portrait:
        assert portrait.size == (900, 1200)
        assert max(portrait.getpixel((0, 600))) < 20
    assert [item["format"] for item in public["previews"]] == ["landscape", "portrait"]
    for preview, size in zip(public["previews"], ((320, 240), (240, 320)), strict=True):
        image_data = base64.b64decode(preview["jpeg_base64"], validate=True)
        assert len(image_data) <= 32_768
        with Image.open(io.BytesIO(image_data)) as image:
            assert image.format == "JPEG"
            assert image.size == size
    assert all("path" not in key for key in public)

    if os.name == "posix":
        cover_dir = private["source_path"].parent
        assert stat.S_IMODE((data_dir / "covers").stat().st_mode) == 0o700
        assert stat.S_IMODE(cover_dir.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(cover_dir.stat().st_mode) == 0o700
        for path in cover_dir.iterdir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_normalized_duplicate_is_idempotent_and_identity_binds_release_and_video(tmp_path):
    data_dir, _video_path, store = _store(tmp_path)
    first_png = _image_bytes("PNG", note="first encoding")
    second_png = _image_bytes("PNG", note="different metadata")

    first = store.import_image("ep00", first_png)
    cover_dir = data_dir / "covers" / "ep00" / "uploads" / first["cover_id"]
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in cover_dir.iterdir()}
    second = store.import_image("ep00", second_png)

    assert first["cover_id"] == second["cover_id"]
    assert first["cover_sha256"] == second["cover_sha256"]
    assert before == {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in cover_dir.iterdir()}

    other_data = tmp_path / "other-state"
    _write_release(other_data, "ep01", b"original video")
    other_store = covers.CoverStore(other_data, releases.ReleaseStore(other_data))
    different_release = other_store.import_image("ep01", first_png)
    assert different_release["cover_sha256"] == first["cover_sha256"]
    assert different_release["cover_id"] != first["cover_id"]

    changed_data = tmp_path / "changed-video-state"
    _write_release(changed_data, "ep00", b"different video")
    changed_store = covers.CoverStore(changed_data, releases.ReleaseStore(changed_data))
    different_video = changed_store.import_image("ep00", first_png)
    assert different_video["cover_sha256"] == first["cover_sha256"]
    assert different_video["video_sha256"] != first["video_sha256"]
    assert different_video["cover_id"] != first["cover_id"]


def test_import_rejects_oversized_unsupported_animated_and_bomb_images(tmp_path):
    _data_dir, _video_path, store = _store(tmp_path)
    with pytest.raises(covers.CoverError, match="大小"):
        store.import_image("ep00", b"x" * (covers.MAX_IMAGE_BYTES + 1))
    with pytest.raises(covers.CoverError, match="JPEG、PNG 或 WebP"):
        store.import_image("ep00", _image_bytes("GIF"))
    with pytest.raises(covers.CoverError, match="无效"):
        store.import_image("ep00", b"not an image")

    first = Image.new("RGB", (8, 8), "red")
    second = Image.new("RGB", (8, 8), "blue")
    animation = io.BytesIO()
    try:
        first.save(animation, format="WEBP", save_all=True, append_images=[second], duration=100, loop=0)
    except (OSError, ValueError) as exc:
        pytest.skip(f"当前 Pillow 未启用 WebP 编码：{exc}")
    with pytest.raises(covers.CoverError, match="动画"):
        store.import_image("ep00", animation.getvalue())

    bomb = io.BytesIO()
    Image.new("RGB", (4001, 4000), "black").save(bomb, format="PNG")
    with pytest.raises(covers.CoverError, match="像素数"):
        store.import_image("ep00", bomb.getvalue())


def test_frames_extracts_three_default_frames_safely_and_preserves_original(tmp_path, monkeypatch):
    _data_dir, video_path, store = _store(tmp_path)
    original_video = video_path.read_bytes()
    frame = _image_bytes("JPEG", color=(20, 90, 210))
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).write_bytes(frame)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(covers.subprocess, "run", fake_run)
    result = store.frames("ep00")

    assert len(result) == 3
    assert [item["time"] for item in result] == pytest.approx([63.25 * 0.25, 63.25 * 0.5, 63.25 * 0.75])
    assert all(item["source"] == "video_frame" for item in result)
    assert all("video_path" not in item and "landscape_path" not in item for item in result)
    assert len(calls) == 3
    for command, options in calls:
        assert options["shell"] is False
        assert options["check"] is True
        assert options["timeout"] == covers.FFMPEG_TIMEOUT_SECONDS
        assert command[0] == "ffmpeg"
        assert command[command.index("-i") + 1] == os.fspath(video_path)
    assert video_path.read_bytes() == original_video


@pytest.mark.parametrize("times", [[-0.1], [63.25], [float("nan")], [float("inf")], [True], [0] * 6, "1"])
def test_frames_rejects_invalid_times_before_calling_ffmpeg(tmp_path, monkeypatch, times):
    _data_dir, _video_path, store = _store(tmp_path)
    monkeypatch.setattr(
        covers.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("ffmpeg must not run for invalid times"),
    )

    with pytest.raises(covers.CoverError):
        store.frames("ep00", times=times)


def test_frames_rejects_unrepresentably_large_integer_time(tmp_path, monkeypatch):
    _data_dir, _video_path, store = _store(tmp_path)
    monkeypatch.setattr(
        covers.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("ffmpeg must not run for invalid times"),
    )

    with pytest.raises(covers.CoverError):
        store.frames("ep00", times=[10**1000])


def test_frames_propagates_ffmpeg_failures_and_accepts_at_most_five_times(tmp_path, monkeypatch):
    _data_dir, _video_path, store = _store(tmp_path)
    with pytest.raises(covers.CoverError, match="最多"):
        store.frames("ep00", times=[0, 1, 2, 3, 4, 5])

    error = subprocess.CalledProcessError(2, ["ffmpeg"], stderr=b"decode failed")
    monkeypatch.setattr(covers.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(subprocess.CalledProcessError):
        store.frames("ep00", times=[1])

    timeout = subprocess.TimeoutExpired(["ffmpeg"], 30)
    monkeypatch.setattr(covers.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(timeout))
    with pytest.raises(subprocess.TimeoutExpired):
        store.frames("ep00", times=[1])


def test_existing_id_with_tampered_file_fails_closed_without_replacing_it(tmp_path):
    _data_dir, _video_path, store = _store(tmp_path)
    image = _image_bytes("PNG")
    public = store.import_image("ep00", image)
    tampered = tmp_path / "state" / "covers" / "ep00" / "uploads" / public["cover_id"] / "portrait.jpg"
    tampered.write_bytes(b"changed")

    with pytest.raises(covers.CoverError, match="摘要不一致"):
        store.import_image("ep00", image)
    assert tampered.read_bytes() == b"changed"


def test_unchanged_legacy_cover_derivatives_remain_loadable(tmp_path):
    _data_dir, _video_path, store = _store(tmp_path)
    public = store.import_image("ep00", _image_bytes("PNG", size=(77, 31)))
    private = store.load("ep00", public["cover_id"])
    with Image.open(private["source_path"]) as source_image:
        source = source_image.convert("RGB")

    for name, size in (("landscape", (1200, 900)), ("portrait", (900, 1200))):
        padded = ImageOps.pad(
            source,
            size,
            method=Image.Resampling.LANCZOS,
            color=(0, 0, 0),
            centering=(0.5, 0.5),
        )
        legacy = io.BytesIO()
        padded.save(
            legacy,
            format="JPEG",
            quality=90,
            optimize=True,
            progressive=False,
            subsampling=0,
        )
        assert legacy.getvalue() == private[f"{name}_path"].read_bytes()

    assert store.load("ep00", public["cover_id"])["cover_id"] == public["cover_id"]


def test_load_rejects_cover_bytes_with_coordinated_manifest_digest(tmp_path):
    _data_dir, _video_path, store = _store(tmp_path)
    public = store.import_image("ep00", _image_bytes("PNG"))
    cover_dir = tmp_path / "state" / "covers" / "ep00" / "uploads" / public["cover_id"]
    landscape = cover_dir / "landscape.jpg"
    changed_bytes = _image_bytes("JPEG", color=(0, 190, 40), size=(1200, 900))
    landscape.write_bytes(changed_bytes)

    manifest_path = cover_dir / "cover.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["landscape.jpg"] = hashlib.sha256(changed_bytes).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(covers.CoverError, match="与规范化原图导出结果不一致"):
        store.load("ep00", public["cover_id"])
    with pytest.raises(covers.CoverError, match="与规范化原图导出结果不一致"):
        store.import_image("ep00", _image_bytes("PNG"))
    assert landscape.read_bytes() == changed_bytes


def test_load_rejects_symlinked_cover_assets(tmp_path, monkeypatch):
    _data_dir, _video_path, store = _store(tmp_path)
    public = store.import_image("ep00", _image_bytes())
    cover_dir = tmp_path / "state" / "covers" / "ep00" / "uploads" / public["cover_id"]
    asset = cover_dir / "landscape.jpg"
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(asset.read_bytes())
    asset.unlink()
    try:
        asset.symlink_to(outside)
    except (OSError, NotImplementedError):
        real_lstat = covers.os.lstat

        def lstat_with_asset_link(path):
            if Path(path) == asset:
                return os.stat_result(
                    (stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, outside.stat().st_size, 0, 0, 0)
                )
            return real_lstat(path)

        monkeypatch.setattr(covers.os, "lstat", lstat_with_asset_link)

    with pytest.raises(covers.CoverError):
        store.load("ep00", public["cover_id"])


def test_cover_identity_is_invalidated_when_release_video_changes(tmp_path):
    data_dir, _video_path, store = _store(tmp_path)
    public = store.import_image("ep00", _image_bytes())
    package = data_dir / "releases" / "ep00"
    changed_video = b"new original video"
    (package / "video.mp4").write_bytes(changed_video)
    (package / "manifest.json").write_text(
        json.dumps(_manifest("ep00", changed_video)), encoding="utf-8"
    )

    with pytest.raises(covers.CoverError, match="原视频已变化"):
        store.load("ep00", public["cover_id"])


def test_load_rejects_malformed_manifest_fields(tmp_path):
    _data_dir, _video_path, store = _store(tmp_path)
    public = store.import_image("ep00", _image_bytes())
    manifest_path = (
        tmp_path / "state" / "covers" / "ep00" / "uploads" / public["cover_id"] / "cover.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(covers.CoverError):
        store.load("ep00", public["cover_id"])


def test_classified_layout_keeps_legacy_idempotency_and_rejects_ambiguous_copy(tmp_path):
    data_dir, _, store = _store(tmp_path)
    image = _image_bytes()
    public = store.import_image("ep00", image)
    directory = store.load("ep00", public["cover_id"])["source_path"].parent
    assert directory.parent.name == "uploads"
    original = {p.name: p.read_bytes() for p in directory.iterdir()}
    legacy = data_dir / "covers" / "ep00" / public["cover_id"]
    directory.rename(legacy)
    assert store.load("ep00", public["cover_id"])["source_path"].parent == legacy
    assert store.import_image("ep00", image)["cover_id"] == public["cover_id"]
    assert original == {p.name: p.read_bytes() for p in legacy.iterdir()}
    shutil.copytree(legacy, directory)
    with pytest.raises(covers.CoverError, match="多份"):
        store.load("ep00", public["cover_id"])
    with pytest.raises(covers.CoverError, match="多份"):
        store.catalog()


def test_catalog_paginates_existing_assets_without_generating_frames(tmp_path):
    _, _, store = _store(tmp_path)
    expected = {store.import_image("ep00", _image_bytes(color=(i * 35, 20, 30)))["cover_id"] for i in range(6)}
    first = store.catalog()
    second = store.catalog("ep00", first["next_offset"])
    assert first["total"] == second["total"] == 6
    assert len(first["covers"]) == 5
    assert second["next_offset"] is None
    assert {c["cover_id"] for c in first["covers"] + second["covers"]} == expected
    with pytest.raises(covers.CoverError):
        store.catalog(offset=True)


def test_library_reuse_rebinds_target_identity_and_preserves_original(tmp_path):
    data_dir, _, store = _store(tmp_path)
    _write_release(data_dir, "ep01", b"target video")
    original = store.import_image("ep00", _image_bytes())
    source = store.load("ep00", original["cover_id"])
    source_bytes = source["source_path"].read_bytes()
    reused = store.reuse("ep01", "ep00", original["cover_id"])
    assert reused["cover_id"] != original["cover_id"]
    assert reused["cover_sha256"] == original["cover_sha256"]
    assert reused["source"] == "library_image"
    assert "time" not in reused
    target = store.load("ep01", reused["cover_id"])
    assert target["source_path"].parent.parent.name == "reused"
    assert target["source_path"].read_bytes() == source_bytes == source["source_path"].read_bytes()
    same = store.reuse("ep00", "ep00", original["cover_id"])
    assert same["cover_id"] == original["cover_id"]
    assert same["source"] == "qq_image"
    assert not (data_dir / "covers" / "ep00" / "reused").exists()


def test_category_mismatch_and_reuse_of_tampered_source_are_rejected(tmp_path):
    data_dir, _, store = _store(tmp_path)
    original = store.import_image("ep00", _image_bytes())
    directory = store.load("ep00", original["cover_id"])["source_path"].parent
    other = directory.parent.parent / "frames"
    other.mkdir(mode=0o700)
    directory.rename(other / directory.name)
    with pytest.raises(covers.CoverError, match="分类"):
        store.load("ep00", original["cover_id"])
    with pytest.raises(covers.CoverError, match="分类"):
        store.reuse("ep01", "ep00", original["cover_id"])


def test_catalog_reports_persistent_origin_when_same_pixels_arrive_from_another_source(tmp_path):
    _, _, store = _store(tmp_path)
    imported = store.import_image("ep00", _image_bytes())
    private = store.load("ep00", imported["cover_id"])
    requested = store._install(store._release("ep00"), private["source_path"].read_bytes(), source="video_frame", time=1.0)
    assert requested["cover_id"] == imported["cover_id"]
    assert requested["source"] == "video_frame" and requested["time"] == 1.0
    saved = store.catalog()["covers"][0]
    assert saved["source"] == "qq_image" and "time" not in saved


def test_release_named_frames_cannot_hide_a_wrong_category(tmp_path):
    _, _, store = _store(tmp_path, release_id="frames")
    imported = store.import_image("frames", _image_bytes())
    directory = store.load("frames", imported["cover_id"])["source_path"].parent
    incorrect_parent = directory.parent.parent / "frames"
    incorrect_parent.mkdir(mode=0o700)
    directory.rename(incorrect_parent / directory.name)
    with pytest.raises(covers.CoverError, match="分类"):
        store.load("frames", imported["cover_id"])
