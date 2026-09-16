"""通过 SSH 隧道调用工作站 TTS；命令提供方输出格式应设为 wav。"""

import json
import io
import os
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path


def synthesize(input_path, output_path, metadata_path=None):
    output = Path(output_path)
    if output.suffix.lower() != ".wav":
        raise ValueError("remote_gptsovits 命令提供方的 format 必须为 wav")
    text = Path(input_path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("语音文本不能为空")
    payload = {"text": text, "media_type": "wav", "streaming_mode": False}
    if metadata_path:
        metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata 必须是 JSON 对象")
        for key in ("scene", "profile", "reference"):
            value = metadata.get(key)
            if value is not None:
                if not isinstance(value, str) or not value.strip() or len(value) > 128:
                    raise ValueError(f"{key} 必须是 1 至 128 字符的非空名称")
                payload[key] = value.strip()
    req = urllib.request.Request(
        "http://127.0.0.1:19880/tts",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # 合成请求只发送一次，避免超时后重复占用工作站生成资源。
    with urllib.request.urlopen(req, timeout=290) as response:
        audio = response.read()
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            expected = wav.getnframes() * wav.getnchannels() * wav.getsampwidth()
            if expected <= 0 or len(wav.readframes(wav.getnframes())) != expected:
                raise ValueError("工作站返回的 WAV 音频为空或已截断")
    except (wave.Error, EOFError) as exc:
        raise ValueError("工作站未返回有效 WAV 音频") from exc
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".tts-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(audio)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit("用法：tts_remote_gptsovits_bridge.py input output [metadata]")
    try:
        synthesize(*sys.argv[1:])
    except Exception as exc:
        print(f"TTS 转发失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
