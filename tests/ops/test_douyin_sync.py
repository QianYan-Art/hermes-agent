from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


OPS_DIR = Path(__file__).parents[2] / "ops" / "douyin-login"
if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))

import stage_release

SYNC_SPEC = importlib.util.spec_from_file_location("douyin_sync_openfilm", OPS_DIR / "sync_openfilm.py")
assert SYNC_SPEC is not None and SYNC_SPEC.loader is not None
sync = importlib.util.module_from_spec(SYNC_SPEC)
sys.modules[SYNC_SPEC.name] = sync
SYNC_SPEC.loader.exec_module(sync)


def _config(tmp_path: Path) -> sync.SyncConfig:
    identity_file = tmp_path / "id_ed25519"
    identity_file.write_text("private test fixture", encoding="utf-8")
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    return sync.SyncConfig("example.test", "hermes", 2222, identity_file, projects_root)


def _manifest(video: bytes, release_id: str = "ep00") -> dict[str, object]:
    return {
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
        "source": "OpenFilm Studio，字幕已烧录",
    }


def _stub_probe(monkeypatch):
    monkeypatch.setattr(
        stage_release,
        "probe_video",
        lambda _path: {"duration": 63.25, "width": 1920, "height": 1080, "fps": 30.0},
    )


@pytest.mark.parametrize("size", [689392111, 2 * 1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024 + 1])
def test_sync_video_size_matches_two_gib_server_limit(tmp_path, monkeypatch, size):
    """仅替换文件大小元数据，路径校验仍走真实小文件。"""
    config = _config(tmp_path)
    video = config.projects_root / "episode.mp4"
    video.write_bytes(b"fixture")
    monkeypatch.setattr(sync, "_file_state", lambda _path: (1, 2, size, 4))
    if size > 2 * 1024 * 1024 * 1024:
        with pytest.raises(sync.SyncError, match="2 GiB"):
            sync._validate_video_path(video, config.projects_root)
    else:
        assert sync._validate_video_path(video, config.projects_root)[1][2] == size


def _subprocess_success(monkeypatch, digest: str, size: int, *, initial_state: str = "missing", mutate_video=None):
    remote_directory = "/tmp/hermes-douyin-upload.AbCdEf1234"
    calls: list[list[str]] = []
    inspect_count = 0

    def fake_run(arguments, **_kwargs):
        nonlocal inspect_count
        args = list(arguments)
        calls.append(args)
        if args[0] == "scp":
            if args[-1].endswith(":/manifest.json"):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if args[-1].endswith(":/video.mp4"):
                if mutate_video is not None:
                    mutate_video(Path(args[-2]))
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if args[-1].endswith("/manifest.json"):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if args[-1].endswith("/video.mp4"):
                if mutate_video is not None:
                    mutate_video(Path(args[-2]))
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            raise AssertionError(args)
        command = args[-1]
        if command.startswith("umask 077 &&"):
            output = remote_directory + "\n"
        elif "from releases import ReleaseStore" in command:
            inspect_count += 1
            state = initial_state if inspect_count == 1 else "same"
            if state == "same":
                output = json.dumps({"state": "same", "hash": digest, "bytes": size}) + "\n"
            else:
                output = json.dumps({"state": state}) + "\n"
        elif "import hashlib, json, os, sys" in command:
            output = json.dumps({"hash": digest, "bytes": size}) + "\n"
        elif "stage_release.py" in command:
            output = "{}\n"
        elif "rm -rf" in command:
            output = ""
        else:
            raise AssertionError(command)
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(sync.subprocess, "run", fake_run)
    return calls


def test_sync_emits_structured_success_and_uploads_only_manifest_and_video(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path)
    video = config.projects_root / "episode.mp4"
    video_bytes = b"already-exported-video"
    video.write_bytes(video_bytes)
    digest = hashlib.sha256(video_bytes).hexdigest()
    _stub_probe(monkeypatch)
    calls = _subprocess_success(monkeypatch, digest, len(video_bytes))
    config_path = tmp_path / "hermes-publish.json"
    config_path.write_text(
        json.dumps(
            {
                "host": config.host,
                "user": config.user,
                "port": config.port,
                "identity_file": str(config.identity_file),
                "projects_root": str(config.projects_root),
            }
        ),
        encoding="utf-8",
    )

    result = sync.main(
        [
            "--config",
            str(config_path),
            "--video",
            str(video),
            "--release-id",
            "ep00",
            "--title",
            "序栞：第一集",
            "--description",
            "已导出并烧录字幕。",
            "--source",
            "OpenFilm Studio，字幕已烧录",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "release_id": "ep00",
        "hash": digest,
        "bytes": len(video_bytes),
        "synced": True,
    }
    uploads = [call[-1] for call in calls if call[0] == "scp"]
    assert [target.rsplit(":", 1)[-1].rsplit("/", 1)[-1] for target in uploads] == ["manifest.json", "video.mp4"]
    assert all(
        "BatchMode=yes" in call and "StrictHostKeyChecking=yes" in call and "IdentitiesOnly=yes" in call
        for call in calls
        if call[0] in {"ssh", "scp"}
    )
    install_calls = [call for call in calls if call[0] == "ssh" and "stage_release.py" in call[-1]]
    assert len(install_calls) == 1


def test_same_release_and_materials_skip_video_upload(tmp_path, monkeypatch):
    config = _config(tmp_path)
    video = config.projects_root / "episode.mp4"
    video_bytes = b"already-exported-video"
    video.write_bytes(video_bytes)
    digest = hashlib.sha256(video_bytes).hexdigest()
    _stub_probe(monkeypatch)
    calls = _subprocess_success(monkeypatch, digest, len(video_bytes), initial_state="same")

    result = sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。", "OpenFilm Studio，字幕已烧录")

    assert result == {"release_id": "ep00", "hash": digest, "bytes": len(video_bytes), "synced": True}
    uploads = [call[-1] for call in calls if call[0] == "scp"]
    assert len(uploads) == 1 and uploads[0].endswith("/manifest.json")
    assert not any(call[0] == "ssh" and "stage_release.py" in call[-1] for call in calls)


def test_same_release_id_with_different_materials_is_rejected(tmp_path, monkeypatch):
    config = _config(tmp_path)
    video = config.projects_root / "episode.mp4"
    video.write_bytes(b"already-exported-video")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    _stub_probe(monkeypatch)
    calls = _subprocess_success(monkeypatch, digest, video.stat().st_size, initial_state="conflict")

    with pytest.raises(sync.SyncError, match="拒绝覆盖"):
        sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。")
    assert not any(call[0] == "scp" and call[-1].endswith(":/video.mp4") for call in calls)
    assert any(call[0] == "ssh" and "rm -rf" in call[-1] for call in calls)


def test_failure_still_cleans_valid_remote_temporary_directory(tmp_path, monkeypatch):
    config = _config(tmp_path)
    video = config.projects_root / "episode.mp4"
    video.write_bytes(b"already-exported-video")
    _stub_probe(monkeypatch)
    calls: list[list[str]] = []

    def fake_run(arguments, **_kwargs):
        args = list(arguments)
        calls.append(args)
        if args[0] == "ssh" and args[-1].startswith("umask 077 &&"):
            return SimpleNamespace(returncode=0, stdout="/tmp/hermes-douyin-upload.AbCdEf1234\n", stderr="")
        if args[0] == "scp":
            return SimpleNamespace(returncode=7, stdout="", stderr="private key or remote details must not escape")
        if args[0] == "ssh" and "rm -rf" in args[-1]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(sync.subprocess, "run", fake_run)

    with pytest.raises(sync.SyncError, match="退出码 7") as error:
        sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。")
    assert "private key" not in str(error.value)
    assert calls[-1][0] == "ssh" and "rm -rf" in calls[-1][-1]


def test_video_change_during_scp_aborts_before_install_and_cleans_up(tmp_path, monkeypatch):
    config = _config(tmp_path)
    video = config.projects_root / "episode.mp4"
    video_bytes = b"already-exported-video"
    video.write_bytes(video_bytes)
    digest = hashlib.sha256(video_bytes).hexdigest()
    _stub_probe(monkeypatch)
    calls = _subprocess_success(
        monkeypatch,
        digest,
        len(video_bytes),
        mutate_video=lambda path: path.write_bytes(b"mutated during transfer"),
    )

    with pytest.raises(sync.SyncError, match="发生变化"):
        sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。")

    assert not any(call[0] == "ssh" and "stage_release.py" in call[-1] for call in calls)
    assert any(call[0] == "ssh" and "rm -rf" in call[-1] for call in calls)


def test_video_outside_projects_root_is_rejected(tmp_path, monkeypatch):
    config = _config(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    monkeypatch.setattr(sync.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("不应访问远端"))

    with pytest.raises(sync.SyncError, match="projects_root"):
        sync.sync_release(config, outside, "ep00", "序栞：第一集", "已导出并烧录字幕。")


def test_video_symlink_cannot_escape_projects_root(tmp_path, monkeypatch):
    config = _config(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    link = config.projects_root / "episode.mp4"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"当前环境不能创建符号链接：{exc}")
    monkeypatch.setattr(sync.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("不应访问远端"))

    with pytest.raises(sync.SyncError, match="符号链接|projects_root"):
        sync.sync_release(config, link, "ep00", "序栞：第一集", "已导出并烧录字幕。")


@pytest.mark.parametrize(
    "override",
    [
        {"host": "server;id"},
        {"user": "hermes;id"},
        {"server_source": "/opt/hermes-douyin;id"},
    ],
)
def test_config_rejects_shell_injection(tmp_path, override):
    config = _config(tmp_path)
    payload = {
        "host": config.host,
        "user": config.user,
        "port": config.port,
        "identity_file": str(config.identity_file),
        "projects_root": str(config.projects_root),
        "server_source": config.server_source,
    }
    payload.update(override)
    config_path = tmp_path / "bad-config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(sync.SyncError):
        sync.load_config(config_path)


def test_invalid_remote_mktemp_path_is_never_used_for_cleanup(tmp_path, monkeypatch):
    config = _config(tmp_path)
    video = config.projects_root / "episode.mp4"
    video.write_bytes(b"already-exported-video")
    _stub_probe(monkeypatch)
    calls: list[list[str]] = []

    def fake_run(arguments, **_kwargs):
        args = list(arguments)
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="/tmp/untrusted;rm -rf /\n", stderr="")

    monkeypatch.setattr(sync.subprocess, "run", fake_run)

    with pytest.raises(sync.SyncError, match="临时目录路径无效"):
        sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。")
    assert len(calls) == 1


def test_embedded_remote_python_commands_are_valid():
    ast.parse(sync._REMOTE_INSPECT_SCRIPT)
    ast.parse(sync._REMOTE_HASH_SCRIPT)


@pytest.mark.parametrize(
    ("upload_fails", "cleanup_fails"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_manifest_temp_is_video_local_and_always_removed(tmp_path, monkeypatch, upload_fails, cleanup_fails):
    config = _config(tmp_path)
    video = config.projects_root / "episode.mp4"
    video_bytes = b"already-exported-video"
    video.write_bytes(video_bytes)
    digest = hashlib.sha256(video_bytes).hexdigest()
    remote_directory = "/tmp/hermes-douyin-upload.AbCdEf1234"
    _stub_probe(monkeypatch)

    manifest_directories: list[Path] = []
    upload_count = 0
    inspect_count = 0
    remote_commands: list[str] = []

    def fake_scp(_config, local_path, _remote_path):
        nonlocal upload_count
        local_path = Path(local_path)
        upload_count += 1
        if local_path == video:
            if upload_fails:
                raise sync.SyncError("模拟视频上传失败")
            return
        assert local_path.name == "manifest.json"
        temporary_directory = local_path.parent
        assert temporary_directory.parent == video.parent
        assert temporary_directory.name.startswith(".tmp-hermes-sync-")
        assert temporary_directory.is_dir()
        manifest_directories.append(temporary_directory)

    def fake_inspect(_config, _remote_directory, _release_id):
        nonlocal inspect_count
        inspect_count += 1
        if inspect_count == 1:
            return {"state": "missing"}
        return {"state": "same", "hash": digest, "bytes": len(video_bytes)}

    def fake_ssh(_config, remote_command, *, timeout=60):
        remote_commands.append(remote_command)
        if cleanup_fails and "rm -rf" in remote_command:
            raise sync.SyncError("模拟远端清理失败")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(sync, "_create_remote_directory", lambda _config: remote_directory)
    monkeypatch.setattr(sync, "_scp", fake_scp)
    monkeypatch.setattr(sync, "_inspect_remote", fake_inspect)
    monkeypatch.setattr(
        sync,
        "_verify_remote_upload",
        lambda _config, _remote: {"hash": digest, "bytes": len(video_bytes)},
    )
    monkeypatch.setattr(sync, "_ssh", fake_ssh)

    if upload_fails and cleanup_fails:
        with pytest.raises(sync.SyncError) as error:
            sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。")
        assert "模拟视频上传失败" in str(error.value)
        assert "远端临时目录清理失败" in str(error.value)
    elif upload_fails:
        with pytest.raises(sync.SyncError, match="模拟视频上传失败"):
            sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。")
    elif cleanup_fails:
        with pytest.raises(sync.SyncError, match="作品已入库并验证，但远端临时目录清理失败"):
            sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。")
    else:
        assert sync.sync_release(config, video, "ep00", "序栞：第一集", "已导出并烧录字幕。") == {
            "release_id": "ep00",
            "hash": digest,
            "bytes": len(video_bytes),
            "synced": True,
        }

    assert len(manifest_directories) == 1
    assert not manifest_directories[0].exists()
    assert list(video.parent.glob(".tmp-hermes-sync-*")) == []
    assert any("rm -rf" in command for command in remote_commands)
