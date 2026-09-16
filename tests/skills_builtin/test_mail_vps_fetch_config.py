"""邮件 helper 的配置外置与缓存回收。

这个脚本原先只存在于服务器的 ``~/.hermes/bin/``，不受版本控制、不随部署走，
连接参数还硬编码在源码里。纳入仓库后仓库是公开的，所以主机、端口、SSH 用户和
私钥路径必须从服务器本地配置读取，且在缺配置时不能回退到任何内置地址。

附带覆盖两个缓存目录的回收——gateway 的缓存清理不认识它们，只有 helper 自己会清。
"""

import importlib.util
import os
import time
from pathlib import Path

import pytest

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "skills_builtin" / "mail-vps-ops" / "bin" / "mail_vps_fetch.py"
)


def _load_helper():
    spec = importlib.util.spec_from_file_location("mail_vps_fetch", _HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def helper():
    return _load_helper()


def _write_config(path: Path, **overrides) -> Path:
    body = overrides.pop("body", None)
    if body is None:
        body = """
host = "mail.example.invalid"
port = 2222

[readonly]
user = "reader"
key = "/keys/ro"

[readwrite]
user = "writer"
key = "/keys/rw"
"""
    path.write_text(body, encoding="utf-8")
    return path


class TestConfigLoading:
    def test_reads_config_from_env_override(self, helper, tmp_path, monkeypatch):
        cfg_path = _write_config(tmp_path / "mail_vps.toml")
        monkeypatch.setenv("HERMES_MAIL_VPS_CONFIG", str(cfg_path))

        cfg = helper._load_config()

        assert cfg["host"] == "mail.example.invalid"
        assert cfg["port"] == 2222
        assert helper._ssh_credentials(cfg, "read-mail") == ("reader", "/keys/ro")
        assert helper._ssh_credentials(cfg, "send-mail") == ("writer", "/keys/rw")

    def test_falls_back_to_hermes_home(self, helper, tmp_path, monkeypatch):
        home = tmp_path / ".hermes"
        home.mkdir()
        _write_config(home / "mail_vps.toml")
        monkeypatch.delenv("HERMES_MAIL_VPS_CONFIG", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(home))

        assert helper._load_config()["host"] == "mail.example.invalid"

    def test_missing_config_raises_without_builtin_fallback(self, helper, tmp_path, monkeypatch):
        """缺配置必须报错，绝不能退回到源码里写死的地址。"""
        monkeypatch.delenv("HERMES_MAIL_VPS_CONFIG", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nonexistent"))

        with pytest.raises(helper.ConfigError) as exc:
            helper._load_config()
        assert "missing_config" in str(exc.value)

    @pytest.mark.parametrize(
        "body, expected",
        [
            ('port = 22\n[readonly]\nuser="a"\nkey="b"\n[readwrite]\nuser="c"\nkey="d"\n',
             "config_missing_host_or_port"),
            ('host = "h"\n[readonly]\nuser="a"\nkey="b"\n[readwrite]\nuser="c"\nkey="d"\n',
             "config_missing_host_or_port"),
            ('host = "h"\nport = 22\n[readwrite]\nuser="c"\nkey="d"\n',
             "config_missing_section:readonly"),
            ('host = "h"\nport = 22\n[readonly]\nuser=""\nkey="b"\n[readwrite]\nuser="c"\nkey="d"\n',
             "config_missing_user_or_key:readonly"),
        ],
    )
    def test_incomplete_config_rejected(self, helper, tmp_path, monkeypatch, body, expected):
        cfg_path = _write_config(tmp_path / "mail_vps.toml", body=body)
        monkeypatch.setenv("HERMES_MAIL_VPS_CONFIG", str(cfg_path))

        with pytest.raises(helper.ConfigError) as exc:
            helper._load_config()
        assert expected in str(exc.value)

    def test_no_real_endpoint_in_source(self):
        """公开仓库里不能出现真实主机名、IP 或 SSH 用户名。"""
        import re

        source = _HELPER.read_text(encoding="utf-8")
        assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", source), "源码中出现疑似 IP 字面量"
        for leaked in ("hermesmail", "qianyan.me", "23333"):
            assert leaked not in source, f"源码中出现不该公开的标识: {leaked}"


class TestCacheDirs:
    def test_defaults_under_hermes_home(self, helper, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        att, links, hours = helper._cache_dirs({})

        assert att == tmp_path / "cache" / "mail_attachments"
        assert links == tmp_path / "cache" / "mail_verification_links"
        assert hours == helper.DEFAULT_RETENTION_HOURS

    def test_explicit_dirs_and_retention(self, helper, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        att, links, hours = helper._cache_dirs({
            "cache": {
                "attachments_dir": str(tmp_path / "a"),
                "links_dir": str(tmp_path / "l"),
                "retention_hours": 72,
            }
        })

        assert att == tmp_path / "a"
        assert links == tmp_path / "l"
        assert hours == 72

    def test_invalid_retention_falls_back_to_default(self, helper, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        _, _, hours = helper._cache_dirs({"cache": {"retention_hours": 0}})
        assert hours == helper.DEFAULT_RETENTION_HOURS


class TestPruneCacheDir:
    def test_removes_only_stale_files(self, helper, tmp_path):
        fresh = tmp_path / "fresh.txt"
        stale = tmp_path / "stale.txt"
        fresh.write_text("a", encoding="utf-8")
        stale.write_text("b", encoding="utf-8")
        old = time.time() - 48 * 3600
        os.utime(stale, (old, old))

        removed = helper.prune_cache_dir(tmp_path, 24)

        assert removed == 1
        assert fresh.exists()
        assert not stale.exists()

    def test_missing_directory_is_noop(self, helper, tmp_path):
        assert helper.prune_cache_dir(tmp_path / "nope", 24) == 0

    def test_subdirectories_are_left_alone(self, helper, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        old = time.time() - 48 * 3600
        os.utime(sub, (old, old))

        assert helper.prune_cache_dir(tmp_path, 24) == 0
        assert sub.exists()


class TestReadCommandRetry:
    """读命令在网络类失败时重试；写命令绝不重试。

    写操作不幂等：ssh 超时不代表远端没执行——邮件可能已经发出、消息可能已经删除，
    只是响应没回来。重试等于重复发信或重复删除。
    """

    @staticmethod
    def _cfg():
        return {
            "host": "h",
            "port": 22,
            "readonly": {"user": "ro", "key": __file__},
            "readwrite": {"user": "rw", "key": __file__},
        }

    def _run(self, helper, monkeypatch, command, side_effect):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            result = side_effect(len(calls))
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(helper.subprocess, "run", fake_run)
        monkeypatch.setattr(helper.time, "sleep", lambda s: None)
        out = helper._run_remote(self._cfg(), command, [command])
        return out, len(calls)

    @staticmethod
    def _proc(returncode, stdout="", stderr=""):
        import types

        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_read_retries_on_timeout(self, helper, monkeypatch):
        import subprocess as sp

        def effect(n):
            if n == 1:
                return sp.TimeoutExpired(cmd="ssh", timeout=30)
            return self._proc(0, '{"ok": true}')

        (rc, stdout, _), calls = self._run(helper, monkeypatch, "list-mailboxes", effect)

        assert calls == 2, "读命令超时后应重试一次"
        assert rc == 0 and '"ok": true' in stdout

    def test_read_retries_on_connect_failure(self, helper, monkeypatch):
        def effect(n):
            if n == 1:
                return self._proc(255, "", "ssh: connect failed")
            return self._proc(0, '{"ok": true}')

        (rc, _, _), calls = self._run(helper, monkeypatch, "read-mail", effect)

        assert calls == 2
        assert rc == 0

    def test_read_does_not_retry_when_remote_replied(self, helper, monkeypatch):
        """远端输出了 JSON 就说明命令跑过了，是业务结果，不该重试。"""
        def effect(n):
            return self._proc(255, '{"ok": false, "error": "mailbox_not_found"}')

        (rc, stdout, _), calls = self._run(helper, monkeypatch, "read-mail", effect)

        assert calls == 1, "远端已应答时不得重试"
        assert "mailbox_not_found" in stdout

    def test_read_gives_up_after_limit(self, helper, monkeypatch):
        import json as _json
        import subprocess as sp

        def effect(n):
            return sp.TimeoutExpired(cmd="ssh", timeout=30)

        (rc, stdout, _), calls = self._run(helper, monkeypatch, "list-attachments", effect)

        assert calls == helper.READ_COMMAND_ATTEMPTS
        payload = _json.loads(stdout)
        assert payload["error"] == "ssh_timeout"
        assert payload["attempts"] == helper.READ_COMMAND_ATTEMPTS

    @pytest.mark.parametrize(
        "command",
        ["send-mail", "reply-mail", "forward-mail", "move-mail-to-trash", "delete-mail"],
    )
    def test_write_never_retries(self, helper, monkeypatch, command):
        import subprocess as sp

        def effect(n):
            return sp.TimeoutExpired(cmd="ssh", timeout=30)

        (rc, stdout, _), calls = self._run(helper, monkeypatch, command, effect)

        assert calls == 1, f"{command} 是写操作，超时后绝不能重试"
        assert "ssh_timeout" in stdout
