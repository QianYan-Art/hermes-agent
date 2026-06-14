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
