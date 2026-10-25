"""公共上传脚本的受限目录校验；不执行上传入口。"""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


UPLOADER = Path(__file__).parents[2] / "ops/douyin-login/hermes-upload.ps1"


@pytest.mark.parametrize("field,value", [
    ("server_source", "/opt/unsafe'; echo injected; '"),
    ("server_source", "/opt/$(id)"),
    ("server_source", "/opt/../root"),
    ("user", "-oProxyCommand=unexpected"),
    ("host", "example.test;id"),
])
def test_public_script_validates_config_before_selecting_video_or_connecting(tmp_path, field, value):
    powershell = shutil.which("pwsh")
    if os.name != "nt" or powershell is None:
        pytest.skip("需要 Windows PowerShell 7")
    identity = tmp_path / "identity"
    identity.write_text("隔离测试占位，不能用于SSH", encoding="utf-8")
    config = {"host": "example.test", "user": "root", "port": 22,
              "identity_file": str(identity), "projects_root": str(tmp_path),
              "server_source": "/opt/hermes-douyin"}
    config[field] = value
    path = tmp_path / "publish.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-File", str(UPLOADER),
         "-ConfigPath", str(path), "-Yes"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
    )
    assert result.returncode != 0
    assert "发布配置校验失败" in result.stderr


@pytest.mark.parametrize("location", ["inside", "sibling", "outside", "empty", "wrong_extension", "junction"])
def test_public_upload_script_rejects_outside_or_linked_video(tmp_path, location):
    powershell = shutil.which("pwsh")
    if os.name != "nt" or powershell is None:
        pytest.skip("需要 Windows PowerShell 7 的真实路径语义")
    root = tmp_path / "Projects"
    root.mkdir()
    outside = tmp_path / "Projects-else"
    outside.mkdir()
    source = outside / "episode.mp4"
    source.write_bytes(b"fixture")
    if location == "junction":
        link = root / "linked"
        linked = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command",
             "New-Item -ItemType Junction -Path $env:HERMES_TEST_LINK -Target $env:HERMES_TEST_OUTSIDE | Out-Null"],
            env={**os.environ, "HERMES_TEST_LINK": str(link), "HERMES_TEST_OUTSIDE": str(outside)},
            capture_output=True, text=True, timeout=20,
        )
        if linked.returncode:
            pytest.skip("当前系统不能创建隔离测试目录联接")
        video = link / "episode.mp4"
    elif location == "sibling":
        video = source
    elif location == "outside":
        video = tmp_path / "episode.mp4"
        video.write_bytes(b"fixture")
    else:
        video = root / ("episode.txt" if location == "wrong_extension" else "episode.mp4")
        video.write_bytes(b"" if location == "empty" else b"fixture")
    script = r"""
        $ErrorActionPreference = 'Stop'
        $parseErrors = $null; $parseTokens = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            $env:HERMES_TEST_UPLOADER, [ref]$parseTokens, [ref]$parseErrors)
        if ($parseErrors.Count) { throw '脚本语法错误' }
        $fn = $ast.Find({ param($n)
            $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Resolve-AllowedVideo'
        }, $true)
        . ([scriptblock]::Create($fn.Extent.Text))
        $ProjectsRoot = $env:HERMES_TEST_ROOT
        try {
            $resolved = Resolve-AllowedVideo $env:HERMES_TEST_VIDEO
            @{allowed=$true; path=$resolved} | ConvertTo-Json -Compress
        } catch { @{allowed=$false} | ConvertTo-Json -Compress }
    """
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "HERMES_TEST_UPLOADER": str(UPLOADER),
                 "HERMES_TEST_ROOT": str(root), "HERMES_TEST_VIDEO": str(video)},
            capture_output=True, text=True, timeout=20, check=True,
        )
        assert json.loads(result.stdout)["allowed"] is (location == "inside")
    finally:
        if location == "junction":
            # 仅删除测试联接本身，不能递归删除其指向的目录。
            os.rmdir(link)
