"""Tests for agent/system_prompt.py — context-file cwd wiring."""

from types import SimpleNamespace
from unittest.mock import patch

from agent.system_prompt import build_system_prompt_parts
from agent.tangyuge_identity import RUNTIME_CHARACTER_SKILL


def test_real_conversation_payload_keeps_one_identity_and_reuses_loaded_context(tmp_path, monkeypatch):
    import copy
    import json
    import socket

    from openai.types.chat import ChatCompletion

    from agent.prompt_builder import clear_skills_system_prompt_cache
    from agent.system_prompt import build_system_prompt, invalidate_system_prompt
    from run_agent import AIAgent
    from tools.skills_tool import skill_view

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("TERMINAL_CWD", str(workspace))
    (tmp_path / "skills").mkdir()
    (tmp_path / "memories").mkdir()
    (tmp_path / "config.yaml").write_text(
        "memory:\n  memory_enabled: true\n  user_profile_enabled: true\n"
        "  nudge_interval: 0\nagent:\n  environment_probe: false\n",
        encoding="utf-8",
    )
    (tmp_path / "SOUL.md").write_text("工作风格：SOUL_STYLE_MARKER，准确而自然。", encoding="utf-8")
    (workspace / "AGENTS.md").write_text("工作区事实：CONTEXT_FACT_MARKER。", encoding="utf-8")
    memory_file = tmp_path / "memories" / "MEMORY.md"
    memory_file.write_text("环境事实：MEMORY_FACT_MARKER。", encoding="utf-8")
    (tmp_path / "memories" / "USER.md").write_text("用户偏好：USER_PREF_MARKER。", encoding="utf-8")

    def no_network(*args, **kwargs):
        raise AssertionError("提示拼接回归不得联网")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    clear_skills_system_prompt_cache(clear_snapshot=True)
    names = ["memory", "skills_list", "skill_view", "skill_manage"]
    tools = [{"type": "function", "function": {
        "name": name, "description": name,
        "parameters": {"type": "object", "properties": {}},
    }} for name in names]
    response = ChatCompletion.model_validate({
        "id": "prompt-audit", "created": 0, "object": "chat.completion",
        "model": "kimi-for-coding",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": "离线拼接检查完成。",
        }}],
    })
    captured = []

    def capture(kwargs):
        captured.append(copy.deepcopy(kwargs))
        return response

    with (
        patch("run_agent.OpenAI"),
        patch("run_agent.get_tool_definitions", return_value=tools),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("hermes_cli.plugins.invoke_hook", return_value=[]),
    ):
        agent = AIAgent(
            api_key="offline-test", provider="custom", model="kimi-for-coding",
            base_url="https://api.kimi.com/coding/v1", api_mode="chat_completions",
            platform="qqbot", quiet_mode=True, skip_context_files=False,
            skip_memory=False,
        )
        agent.compression_enabled = False
        agent.save_trajectories = False
        agent.ephemeral_system_prompt = "当前 QQ 上下文：EPHEMERAL_MARKER。"
        with (
            patch.object(agent, "_interruptible_api_call", side_effect=capture),
            patch.object(agent, "_persist_session"),
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            first = agent.run_conversation("我想聊聊最近读的书。")
            assert first["completed"] is True
            cached = agent._cached_system_prompt
            assert "EPHEMERAL_MARKER" not in cached

            loaded = json.loads(skill_view("tangyuge-roleplay"))
            assert loaded["success"] is True
            history = first["messages"] + [
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "read-roleplay", "type": "function", "function": {
                        "name": "skill_view", "arguments": '{"name":"tangyuge-roleplay"}',
                    },
                }]},
                {"role": "tool", "tool_call_id": "read-roleplay", "content": loaded["content"]},
                {"role": "assistant", "content": "我也想听听你的读法。"},
            ]
            memory_file.write_text("环境事实：UPDATED_MEMORY_MARKER。", encoding="utf-8")
            second = agent.run_conversation("那你先说说你的看法。", conversation_history=history)
            assert second["completed"] is True
            assert agent._cached_system_prompt == cached

        assert len(captured) == 2
        systems = []
        for request in captured:
            system_messages = [m["content"] for m in request["messages"] if m["role"] == "system"]
            assert len(system_messages) == 1
            system = system_messages[0]
            systems.append(system)
            for marker in ["# Tangyuge Identity", "## Runtime Boundaries", "## Character Detail Retrieval",
                           "<available_skills>", "SOUL_STYLE_MARKER", "CONTEXT_FACT_MARKER",
                           "MEMORY_FACT_MARKER", "USER_PREF_MARKER", "EPHEMERAL_MARKER"]:
                assert system.count(marker) == 1, marker
            assert "load the `hermes-agent` skill" not in system
            assert "patch it immediately" not in system
            assert "UPDATED_MEMORY_MARKER" not in system
            assert "视为满足读取要求" in system
        assert systems[0] == systems[1]
        assert any(m["role"] == "tool" and m.get("tool_call_id") == "read-roleplay"
                   for m in captured[1]["messages"])

        invalidate_system_prompt(agent)
        rebuilt = build_system_prompt(agent)
        assert rebuilt.count("UPDATED_MEMORY_MARKER") == 1
        assert "MEMORY_FACT_MARKER" not in rebuilt
        assert rebuilt.count("## Character Detail Retrieval") == 1
        assert "EPHEMERAL_MARKER" not in rebuilt
    clear_skills_system_prompt_cache(clear_snapshot=True)


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
    def test_character_skill_guidance_is_stable_and_does_not_preload_resources(self):
        for tools in ([], ["skills_list", "skill_view"]):
            with patch("tools.skills_tool.skill_view") as view:
                first = build_system_prompt_parts(
                    _make_agent(skip_context_files=True, valid_tool_names=tools)
                )
                second = build_system_prompt_parts(
                    _make_agent(skip_context_files=True, valid_tool_names=tools)
                )

            assert first["stable"] == second["stable"]
            assert first["stable"].count(RUNTIME_CHARACTER_SKILL) == 1
            assert RUNTIME_CHARACTER_SKILL not in first["volatile"]
            view.assert_not_called()

    def test_tangyuge_identity_is_first_stable_block(self):
        parts = build_system_prompt_parts(_make_agent(skip_context_files=True))

        assert parts["stable"].startswith("# Tangyuge Identity")
        assert "唐语歌" in parts["stable"]
        assert "You are Hermes Agent" not in parts["stable"]
        assert "created by Nous Research" not in parts["stable"]
        assert "You run on Hermes Agent" not in parts["stable"]

    def test_soul_md_is_overlay_after_tangyuge_identity(self):
        agent = _make_agent(load_soul_identity=True, skip_context_files=True)
        with patch("run_agent.load_soul_md", return_value="SOUL OVERLAY"):
            parts = build_system_prompt_parts(agent)

        assert parts["stable"].index("# Tangyuge Identity") < parts["stable"].index("SOUL OVERLAY")

    def test_skills_prompt_is_overlay_after_tangyuge_identity(self):
        agent = _make_agent(
            skip_context_files=True,
            valid_tool_names=["skills_list", "skill_view"],
        )
        with patch("run_agent.build_skills_system_prompt", return_value="SKILLS PROMPT"):
            parts = build_system_prompt_parts(agent)

        assert parts["stable"].index("# Tangyuge Identity") < parts["stable"].index("SKILLS PROMPT")

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

    def test_fork_help_does_not_require_removed_upstream_skill(self):
        parts = build_system_prompt_parts(_make_agent(skip_context_files=True))

        assert "docs/tangyuge-hermes" in parts["stable"]
        assert "hermes-md-locator" in parts["stable"]
        assert "skill_view(name='hermes-agent')" not in parts["stable"]
        assert "always holds the latest" not in parts["stable"]

    def test_memory_guidance_does_not_require_unavailable_history_tool(self):
        parts = build_system_prompt_parts(
            _make_agent(skip_context_files=True, valid_tool_names=["memory"])
        )

        assert "use session_search" not in parts["stable"]
        assert "enabled history-search tool" in parts["stable"]

    def test_identity_and_execution_have_explicit_separate_scopes(self):
        parts = build_system_prompt_parts(_make_agent(skip_context_files=True))

        assert parts["stable"].count("## Runtime Boundaries") == 1
        assert "角色关系约定不是用户身份验证或权限检查的替代品" in parts["stable"]
        assert "能力以本轮实际提供的工具及其参数为准" in parts["stable"]
