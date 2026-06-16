from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.tangyuge_identity import (
    TangyugeIdentityError,
    build_tangyuge_identity_prompt,
    load_tangyuge_character,
)


def test_runtime_character_json_excludes_chat_openers_and_html_panel():
    data = load_tangyuge_character()

    assert data["name"] == "唐语歌"
    assert "first_mes" not in data
    assert "alternate_greetings" not in data
    assert "scenario" not in data
    assert "post_history_instructions" not in data
    serialized = json.dumps(data, ensure_ascii=False)
    assert "details open" not in serialized
    assert "面板" not in serialized
    assert "状态栏" not in serialized
    assert "总结面板" not in serialized
    assert "好感度" not in serialized
    assert "情绪·" not in serialized
    assert "SillyTavern" not in serialized
    assert "烟火大会" not in serialized
    assert data["provenance"]["source_filename"] == "唐语歌-恋人卡-v1.png"


def test_roleplay_skill_does_not_reintroduce_panel_or_identity_noise():
    skill = Path("skills_builtin/tangyuge-roleplay/SKILL.md").read_text(
        encoding="utf-8"
    )

    for banned in [
        "面板",
        "总结面板",
        "状态栏",
        "好感度",
        "SillyTavern",
        "You are Hermes Agent",
        "created by Nous Research",
        "You run on Hermes Agent",
    ]:
        assert banned not in skill


def test_runtime_character_book_keeps_only_always_on_entries():
    data = load_tangyuge_character()
    entries = data["character_book"]["entries"]

    assert len(entries) == 2
    assert all(entry.get("constant") is True for entry in entries)
    assert [entry["keys"] for entry in entries] == [["唐语歌"], ["场景"]]


def test_build_tangyuge_identity_prompt_is_deterministic_and_high_priority():
    prompt1 = build_tangyuge_identity_prompt()
    prompt2 = build_tangyuge_identity_prompt()

    assert prompt1 == prompt2
    assert prompt1.startswith("# Tangyuge Identity")
    assert "highest-priority identity block" in prompt1
    assert "唐语歌" in prompt1
    assert "## Scenario" not in prompt1
    assert "烟火大会" not in prompt1
    assert "{{original}}" not in prompt1


def test_missing_character_file_fails_closed(tmp_path: Path):
    with pytest.raises(TangyugeIdentityError):
        load_tangyuge_character(tmp_path / "missing.json")
