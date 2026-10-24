"""Tests for delegate_tool toolset scoping.

Verifies that subagents cannot gain tools that the parent does not have.
The LLM controls the `toolsets` parameter — without intersection with the
parent's enabled_toolsets, it can escalate privileges by requesting
arbitrary toolsets.
"""

from types import SimpleNamespace

from tools.delegate_tool import _strip_blocked_tools


class TestToolsetIntersection:
    """Subagent toolsets must be a subset of parent's enabled_toolsets."""

    def test_requested_toolsets_intersected_with_parent(self):
        """LLM requests toolsets parent doesn't have — extras are dropped."""
        parent = SimpleNamespace(enabled_toolsets=["terminal", "file"])

        # Simulate the intersection logic from _build_child_agent
        parent_toolsets = set(parent.enabled_toolsets)
        requested = ["terminal", "file", "web", "browser", "rl"]
        scoped = [t for t in requested if t in parent_toolsets]

        assert sorted(scoped) == ["file", "terminal"]
        assert "web" not in scoped
        assert "browser" not in scoped
        assert "rl" not in scoped

    def test_all_requested_toolsets_available_on_parent(self):
        """LLM requests subset of parent tools — all pass through."""
        parent = SimpleNamespace(enabled_toolsets=["terminal", "file", "web", "browser"])

        parent_toolsets = set(parent.enabled_toolsets)
        requested = ["terminal", "web"]
        scoped = [t for t in requested if t in parent_toolsets]

        assert sorted(scoped) == ["terminal", "web"]

    def test_no_toolsets_requested_inherits_parent(self):
        """When toolsets is None/empty, child inherits parent's set."""
        parent_toolsets = ["terminal", "file", "web"]
        child = _strip_blocked_tools(parent_toolsets)
        assert "terminal" in child
        assert "file" in child
        assert "web" in child

    def test_strip_blocked_removes_mutating_agent_toolsets(self):
        """Blocked toolsets are always removed from default sub-agents."""
        child = _strip_blocked_tools(
            ["terminal", "delegation", "clarify", "memory", "skills"]
        )
        assert "delegation" not in child
        assert "clarify" not in child
        assert "memory" not in child
        assert "skills" not in child
        assert "terminal" in child

    def test_requested_skills_toolset_is_stripped(self):
        """A child cannot regain skill mutation by explicitly requesting skills."""
        child = _strip_blocked_tools(["skills"])

        assert child == []

    def test_empty_intersection_yields_empty_toolsets(self):
        """If parent has no overlap with requested, child gets nothing extra."""
        parent = SimpleNamespace(enabled_toolsets=["terminal"])

        parent_toolsets = set(parent.enabled_toolsets)
        requested = ["web", "browser"]
        scoped = [t for t in requested if t in parent_toolsets]

        assert scoped == []


def _build_child_with_real_tool_schema(
    monkeypatch,
    *,
    hermes_home,
    parent_toolsets,
    parent_disabled_toolsets=None,
    child_toolsets=None,
    role="leaf",
):
    """通过 AIAgent 和真实 model_tools 解析器构建子代理。"""
    import run_agent
    import agent.context_compressor as context_compressor
    import tools.delegate_tool as delegate_tool

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "qqbot")
    monkeypatch.setattr(
        context_compressor,
        "get_model_context_length",
        lambda *args, **kwargs: 128_000,
    )
    monkeypatch.setattr(delegate_tool, "_load_config", lambda: {})
    monkeypatch.setattr(delegate_tool, "_get_orchestrator_enabled", lambda: True)
    monkeypatch.setattr(delegate_tool, "_get_max_spawn_depth", lambda: 3)
    monkeypatch.setattr(
        delegate_tool, "_build_child_progress_callback", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        delegate_tool, "_resolve_child_credential_pool", lambda *args, **kwargs: None
    )
    # AIAgent 仍通过真实解析链生成 schema；这里只 mock 外部客户端构造，测试不调用模型。
    monkeypatch.setattr(
        run_agent.AIAgent,
        "_create_openai_client",
        lambda self, *args, **kwargs: object(),
        raising=False,
    )

    parent = SimpleNamespace(
        _delegate_depth=0,
        enabled_toolsets=parent_toolsets,
        disabled_toolsets=parent_disabled_toolsets,
        model="gpt-4o-mini",
        provider="openai",
        base_url="https://example.invalid/v1",
        api_key="test-key",
        platform="qqbot",
        session_id=None,
    )
    return delegate_tool._build_child_agent(
        task_index=0,
        goal="inspect the effective child tool schema",
        context=None,
        toolsets=child_toolsets,
        model=None,
        max_iterations=1,
        task_count=1,
        parent_agent=parent,
        role=role,
    )


def _schema_tool_names(child):
    return {tool["function"]["name"] for tool in child.tools}


def test_child_schema_blocks_inherited_messaging_toolset(monkeypatch, tmp_path):
    child = _build_child_with_real_tool_schema(
        monkeypatch,
        hermes_home=tmp_path,
        parent_toolsets=["messaging"],
    )

    assert "send_message" not in child.valid_tool_names
    assert "send_message" not in _schema_tool_names(child)


def test_child_schema_applies_parent_disabled_toolsets_to_composite(monkeypatch, tmp_path):
    child = _build_child_with_real_tool_schema(
        monkeypatch,
        hermes_home=tmp_path,
        parent_toolsets=["hermes-cli"],
        parent_disabled_toolsets=["web"],
    )

    assert "send_message" not in child.valid_tool_names
    assert "send_message" not in _schema_tool_names(child)
    assert "web_search" not in child.valid_tool_names
    assert "web" in child.disabled_toolsets


def test_leaf_blocks_delegation_but_orchestrator_keeps_its_role_grant(
    monkeypatch, tmp_path
):
    leaf = _build_child_with_real_tool_schema(
        monkeypatch,
        hermes_home=tmp_path,
        parent_toolsets=["hermes-cli"],
    )
    orchestrator = _build_child_with_real_tool_schema(
        monkeypatch,
        hermes_home=tmp_path,
        parent_toolsets=["hermes-cli"],
        role="orchestrator",
    )

    assert "delegate_task" not in leaf.valid_tool_names
    assert "delegate_task" not in _schema_tool_names(leaf)
    assert "send_message" not in orchestrator.valid_tool_names
    assert "delegate_task" in orchestrator.valid_tool_names
    assert "delegate_task" in _schema_tool_names(orchestrator)
    assert "delegation" not in orchestrator.disabled_toolsets
