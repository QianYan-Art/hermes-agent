"""Tests for agent/system_prompt.py — context-file cwd wiring."""

from types import SimpleNamespace
from unittest.mock import patch

from agent.system_prompt import build_system_prompt_parts


def _make_agent(**overrides):
    base = dict(
        load_soul_identity=False,
        skip_context_files=False,
        valid_tool_names=[],
        _task_completion_guidance=False,
        _tool_use_enforcement=False,
        _environment_probe=False,
        _kanban_worker_guidance="",
        _memory_store=None,
        _memory_manager=None,
        model="",
        provider="",
        platform="",
        pass_session_id=False,
        session_id="",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _captured_context_cwd(agent):
    """The cwd build_system_prompt_parts hands to build_context_files_prompt."""
    captured = {}

    def fake_context_files(cwd=None, skip_soul=False):
        captured["cwd"] = cwd
        return ""

    with (
        patch("run_agent.load_soul_md", return_value=""),
        patch("run_agent.build_nous_subscription_prompt", return_value=""),
        patch("run_agent.build_environment_hints", return_value=""),
        patch("run_agent.build_context_files_prompt", side_effect=fake_context_files),
    ):
        build_system_prompt_parts(agent)
    return captured["cwd"]


class TestContextFileCwd:
    def test_none_when_terminal_cwd_unset(self, monkeypatch):
        # Unset → None, so discovery falls back to the launch dir inside
        # build_context_files_prompt (the local-CLI #19242 contract).
        monkeypatch.delenv("TERMINAL_CWD", raising=False)
        assert _captured_context_cwd(_make_agent()) is None

    def test_configured_dir_when_terminal_cwd_set(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TERMINAL_CWD", str(tmp_path))
        assert _captured_context_cwd(_make_agent()) == tmp_path


class TestTangyugeIdentityOrdering:
    def test_tangyuge_identity_is_first_stable_block(self):
        parts = build_system_prompt_parts(_make_agent(skip_context_files=True))

        assert parts["stable"].startswith("# Tangyuge Identity")
        assert "唐语歌" in parts["stable"]

    def test_soul_md_is_overlay_after_tangyuge_identity(self):
        agent = _make_agent(load_soul_identity=True, skip_context_files=True)
        with patch("run_agent.load_soul_md", return_value="SOUL OVERLAY"):
            parts = build_system_prompt_parts(agent)

        assert parts["stable"].index("# Tangyuge Identity") < parts["stable"].index("SOUL OVERLAY")

    def test_memory_and_user_profile_remain_volatile_below_identity(self):
        class Store:
            def format_for_system_prompt(self, kind):
                return f"{kind.upper()} BLOCK"

        parts = build_system_prompt_parts(
            _make_agent(
                skip_context_files=True,
                _memory_store=Store(),
                _memory_enabled=True,
                _user_profile_enabled=True,
            )
        )

        assert "MEMORY BLOCK" not in parts["stable"]
        assert "USER BLOCK" not in parts["stable"]
        assert "MEMORY BLOCK" in parts["volatile"]
        assert "USER BLOCK" in parts["volatile"]
