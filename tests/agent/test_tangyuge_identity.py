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
    assert "这套 Hermes/QQ 部署只服务阿颜本人" in prompt1
    assert "所有真实对话里的用户都默认是阿颜" in prompt1
    assert "不代表初次见面或关系重置" in prompt1
    assert "不要说“我叫唐语歌" in prompt1
    assert "日常熟人聊天不主动重报姓名" in prompt1
    assert "初次自我介绍时她会说" not in prompt1
    assert "## Scenario" not in prompt1
    assert "烟火大会" not in prompt1
    assert "{{original}}" not in prompt1


def test_missing_character_file_fails_closed(tmp_path: Path):
    with pytest.raises(TangyugeIdentityError):
        load_tangyuge_character(tmp_path / "missing.json")


@pytest.mark.parametrize("name", ["", "   ", 123, [], None])
def test_invalid_character_name_fails_closed(tmp_path: Path, name):
    path = tmp_path / "character.json"
    path.write_text(json.dumps({"name": name}), encoding="utf-8")

    with pytest.raises(TangyugeIdentityError):
        load_tangyuge_character(path)


def test_new_prompt_build_observes_character_file_updates(tmp_path: Path):
    path = tmp_path / "character.json"
    path.write_text(json.dumps({"name": "角色甲"}), encoding="utf-8")
    first = build_tangyuge_identity_prompt(path)
    path.write_text(json.dumps({"name": "角色乙"}), encoding="utf-8")

    assert "## Name\n角色乙" in build_tangyuge_identity_prompt(path)
    assert "## Name\n角色甲" in first


def test_disabled_constant_entries_are_not_injected(tmp_path: Path):
    path = tmp_path / "character.json"
    data = {
        "name": "测试角色",
        "character_book": {"entries": [
            {"constant": True, "enabled": False, "content": "已停用的旧设定"},
            {"constant": True, "content": "当前有效设定"},
            {"constant": False, "content": "未激活的条件设定"},
        ]},
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    prompt = build_tangyuge_identity_prompt(path)

    assert "当前有效设定" in prompt
    assert "已停用的旧设定" not in prompt
    assert "未激活的条件设定" not in prompt


def test_runtime_character_fields_are_present_without_data_changes():
    data = load_tangyuge_character()
    prompt = build_tangyuge_identity_prompt()

    for field in ("name", "description", "personality", "system_prompt", "mes_example"):
        assert data[field].strip() in prompt
    for entry in data["character_book"]["entries"]:
        if entry.get("constant") is True and entry.get("enabled", True):
            assert entry["content"].strip() in prompt
