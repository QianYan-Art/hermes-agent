"""Todo snapshot authority regressions at compression boundaries."""

from agent.context_compressor import SUMMARY_PREFIX
from agent.conversation_compression import _inject_todo_snapshot
from tools.todo_tool import TODO_INJECTION_HEADER


def _snapshot(label: str) -> str:
    return f"{TODO_INJECTION_HEADER}\n- [ ] {label}"


def test_snapshot_merges_into_real_user_tail():
    compressed = [{"role": "user", "content": "继续处理部署"}]

    _inject_todo_snapshot(compressed, _snapshot("检查服务"))

    assert len(compressed) == 1
    assert compressed[0]["content"].startswith("继续处理部署\n\n")
    assert compressed[0]["content"].endswith("检查服务")
    assert "_todo_snapshot_synthetic" not in compressed[0]


def test_snapshot_refreshes_previous_merge_without_accumulating():
    compressed = [{"role": "user", "content": f"继续处理\n\n{_snapshot('旧任务')}"}]

    _inject_todo_snapshot(compressed, _snapshot("新任务"))

    content = compressed[0]["content"]
    assert content.count(TODO_INJECTION_HEADER) == 1
    assert "旧任务" not in content
    assert "新任务" in content


def test_snapshot_preserves_multimodal_user_content():
    compressed = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
            {"type": "text", "text": _snapshot("旧任务")},
        ],
    }]

    _inject_todo_snapshot(compressed, _snapshot("新任务"))

    parts = compressed[0]["content"]
    assert parts[0]["type"] == "image_url"
    assert sum(TODO_INJECTION_HEADER in str(part) for part in parts) == 1
    assert "新任务" in str(parts[-1])


def test_summary_user_tail_keeps_flagged_standalone_snapshot():
    compressed = [{"role": "user", "content": f"{SUMMARY_PREFIX}\nEarlier work"}]

    _inject_todo_snapshot(compressed, _snapshot("检查服务"))

    assert len(compressed) == 2
    assert compressed[-1]["_todo_snapshot_synthetic"] is True


def test_standalone_snapshot_is_refreshed_in_place():
    compressed = [{
        "role": "user",
        "content": _snapshot("旧任务"),
        "_todo_snapshot_synthetic": True,
    }]

    _inject_todo_snapshot(compressed, _snapshot("新任务"))

    assert len(compressed) == 1
    assert "旧任务" not in compressed[0]["content"]
    assert "新任务" in compressed[0]["content"]
