import json
import shlex
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.tts_remote_gptsovits_bridge import synthesize
from tools import tts_tool


def wav_bytes():
    import io
    import wave
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 240)
    return buffer.getvalue()


def config():
    return {
        "provider": "remote_gptsovits",
        "providers": {"remote_gptsovits": {
            "type": "command", "command": "bridge {input_path} {output_path} {metadata_path}",
            "format": "wav", "voice_compatible": False,
        }},
    }


@pytest.mark.parametrize("selections", [
    {}, {"scene": "soft"}, {"profile": "soft_daily"},
    {"reference": "ref_01"}, {"scene": "soft", "profile": "morning", "reference": "ref_01"},
])
def test_tool_metadata_reaches_http_and_tempfiles_are_removed(tmp_path, selections):
    seen = {}
    paths = []

    def run(command, timeout):
        parts = shlex.split(command, posix=False)
        args = [part.strip("'\"") for part in parts[1:]]
        paths.extend([Path(args[0]), Path(args[2])])
        synthesize(*args)

    def urlopen(req, timeout):
        seen.update(json.loads(req.data))
        assert req.full_url == "http://127.0.0.1:19880/tts"
        assert timeout == 290
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = wav_bytes()
        return response

    with patch.object(tts_tool, "_load_tts_config", return_value=config()), \
         patch.object(tts_tool, "_run_command_tts", side_effect=run), \
         patch("urllib.request.urlopen", side_effect=urlopen):
        result = json.loads(tts_tool.text_to_speech_tool(
            "你好", str(tmp_path / "voice.mp3"), **selections,
        ))
    assert result["success"], result
    assert result["file_path"].endswith(".wav")
    assert seen == {"text": "你好", "media_type": "wav", "streaming_mode": False, **selections}
    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize("value", ["", " ", 123, [], "x" * 129])
def test_invalid_selection_rejected_before_generation(value):
    with patch.object(tts_tool, "_load_tts_config", return_value=config()), \
         patch.object(tts_tool, "_generate_command_tts") as generate:
        result = json.loads(tts_tool.text_to_speech_tool("你好", profile=value))
    assert not result["success"]
    generate.assert_not_called()


def test_other_provider_does_not_silently_drop_selection():
    with patch.object(tts_tool, "_load_tts_config", return_value={"provider": "edge"}):
        result = json.loads(tts_tool.text_to_speech_tool("你好", scene="soft"))
    assert not result["success"]


def test_missing_metadata_placeholder_is_reported():
    cfg = config()
    cfg["providers"]["remote_gptsovits"]["command"] = "bridge {input_path} {output_path}"
    with patch.object(tts_tool, "_load_tts_config", return_value=cfg):
        result = json.loads(tts_tool.text_to_speech_tool("你好", scene="soft"))
    assert not result["success"]
    assert "metadata_path" in result["error"]


def test_metadata_keeps_selection_out_of_shell(tmp_path):
    selection = 'soft"; echo hello; #'
    seen = {}

    def run(command, timeout):
        assert selection not in command
        args = [part.strip("'\"") for part in shlex.split(command, posix=False)[1:]]
        seen.update(json.loads(Path(args[2]).read_text(encoding="utf-8")))
        Path(args[1]).write_bytes(b"audio")

    with patch.object(tts_tool, "_load_tts_config", return_value=config()), \
         patch.object(tts_tool, "_run_command_tts", side_effect=run):
        result = json.loads(tts_tool.text_to_speech_tool(
            "你好", str(tmp_path / "voice.wav"), profile=selection,
        ))
    assert result["success"]
    assert seen["profile"] == selection


def test_registry_forwards_selection(tmp_path):
    handler = tts_tool.registry._tools["text_to_speech"].handler
    with patch.object(tts_tool, "text_to_speech_tool", return_value="ok") as call:
        assert handler({"text": "你好", "profile": "soft_daily", "reference": "ref_01"}) == "ok"
    assert call.call_args.kwargs["profile"] == "soft_daily"
    assert call.call_args.kwargs["reference"] == "ref_01"


def test_http_failure_does_not_retry_or_write_audio(tmp_path):
    import urllib.error
    source = tmp_path / "text.txt"
    source.write_text("你好", encoding="utf-8")
    output = tmp_path / "voice.wav"
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")) as call:
        with pytest.raises(urllib.error.URLError):
            synthesize(source, output)
    assert call.call_count == 1
    assert not output.exists()


@pytest.mark.parametrize("response_bytes", [
    b"", b'{"error":"unavailable"}', b"OggS01234567",
    b"RIFF\x04\x00\x00\x00WAVE", wav_bytes()[:-2],
])
def test_non_wav_response_rejected(tmp_path, response_bytes):
    from unittest.mock import MagicMock
    source = tmp_path / "text.txt"
    source.write_text("你好", encoding="utf-8")
    output = tmp_path / "voice.wav"
    response = MagicMock()
    response.__enter__.return_value.read.return_value = response_bytes
    with patch("urllib.request.urlopen", return_value=response):
        with pytest.raises(ValueError, match="WAV"):
            synthesize(source, output)
    assert not output.exists()


def test_wrong_extension_rejected_before_http(tmp_path):
    with patch("urllib.request.urlopen") as request:
        with pytest.raises(ValueError, match="format"):
            synthesize(tmp_path / "text.txt", tmp_path / "voice.ogg")
    request.assert_not_called()


def test_failed_command_cleans_partial_output_and_metadata(tmp_path):
    import subprocess
    paths = []

    def fail(command, timeout):
        args = [part.strip("'\"") for part in shlex.split(command, posix=False)[1:]]
        paths.extend(map(Path, args))
        Path(args[1]).write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, command, stderr="failed")

    with patch.object(tts_tool, "_load_tts_config", return_value=config()), \
         patch.object(tts_tool, "_run_command_tts", side_effect=fail):
        result = json.loads(tts_tool.text_to_speech_tool("你好", str(tmp_path / "voice.wav")))
    assert not result["success"]
    assert all(not path.exists() for path in paths)
