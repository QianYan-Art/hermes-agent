import json

import agent.skill_utils as skill_utils
from tools.skills_tool import skills_list, skill_view


RETAINED_SKILLS = {
    "grill-me",
    "grok-search",
    "hermes-md-locator",
    "mail-vps-ops",
    "paper-translation-to-docx",
    "tangyuge-roleplay",
}


def test_clean_install_lists_retained_builtin_skills(tmp_path, monkeypatch):
    local_skills = tmp_path / "empty-skills"
    local_skills.mkdir()
    monkeypatch.setattr(skill_utils, "get_skills_dir", lambda: local_skills)
    monkeypatch.setattr(skill_utils, "get_external_skills_dirs", lambda: [])

    result = json.loads(skills_list())

    assert result["success"] is True
    assert {skill["name"] for skill in result["skills"]} == RETAINED_SKILLS


def test_local_same_name_skill_does_not_shadow_builtin(tmp_path, monkeypatch):
    local_skill = tmp_path / "skills" / "tangyuge-roleplay"
    local_skill.mkdir(parents=True)
    (local_skill / "SKILL.md").write_text(
        "---\n"
        "name: tangyuge-roleplay\n"
        "description: LOCAL SHADOW\n"
        "---\n\n"
        "LOCAL VERSION SHOULD NOT LOAD\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(skill_utils, "get_skills_dir", lambda: tmp_path / "skills")
    monkeypatch.setattr(skill_utils, "get_external_skills_dirs", lambda: [])

    listed = json.loads(skills_list())
    viewed = json.loads(skill_view("tangyuge-roleplay"))

    listing = {skill["name"]: skill for skill in listed["skills"]}
    assert listing["tangyuge-roleplay"]["description"] != "LOCAL SHADOW"
    assert viewed["success"] is True
    assert "LOCAL VERSION SHOULD NOT LOAD" not in viewed["content"]


def test_tangyuge_roleplay_supporting_resources_are_viewable():
    for file_path in [
        "soul.md",
        "limit.md",
        "resource/speech_patterns.md",
        "resource/behavior_guide.md",
        "resource/relationship_dynamics.md",
        "resource/key_life_events.md",
    ]:
        viewed = json.loads(skill_view("tangyuge-roleplay", file_path=file_path))

        assert viewed["success"] is True
        assert viewed["content"].strip()


def test_tangyuge_roleplay_does_not_conflict_with_core_identity():
    viewed = json.loads(skill_view("tangyuge-roleplay"))
    content = viewed["content"]

    assert "不得覆盖、替换、重新定义或重复注入主身份" in content
    assert "角色卡和系统提示词优先" in content
    assert "不把原作具名角色带进当前对话" in content
    assert "这套 Hermes/QQ 部署只服务阿颜本人" in content
    assert "新建 session 只是技术会话重开" in content
    assert "不做自我介绍" in content


def test_tangyuge_roleplay_relationships_avoid_named_source_characters():
    viewed = json.loads(skill_view("tangyuge-roleplay", file_path="resource/relationship_dynamics.md"))
    content = viewed["content"]

    assert "何曦铭" not in content
    assert "赵晚滢" not in content
    assert "亲密女性挚友" in content
    assert "恋人 / {{user}}" in content


def test_tangyuge_roleplay_routes_migrated_card_topics():
    viewed = json.loads(skill_view("tangyuge-roleplay"))
    content = viewed["content"]

    for phrase in ["奶奶", "初雪", "文学社", "亲爱的", "甜品", "荷包", "现金"]:
        assert phrase in content

    key_events = json.loads(
        skill_view("tangyuge-roleplay", file_path="resource/key_life_events.md")
    )["content"]
    behavior = json.loads(
        skill_view("tangyuge-roleplay", file_path="resource/behavior_guide.md")
    )["content"]
    relationships = json.loads(
        skill_view("tangyuge-roleplay", file_path="resource/relationship_dynamics.md")
    )["content"]

    assert "老书店" in key_events
    assert "下初雪" in key_events
    assert "《红楼梦》" in key_events
    assert "小荷包" in behavior
    assert "草莓小蛋糕" in behavior
    assert "这位挚友不需要具体登场" in relationships
