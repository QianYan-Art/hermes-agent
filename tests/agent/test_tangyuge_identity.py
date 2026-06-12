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
    assert "post_history_instructions" not in data
    assert "details open" not in json.dumps(data, ensure_ascii=False)
    assert data["provenance"]["source_filename"] == "唐语歌-恋人卡-v1.png"


def test_build_tangyuge_identity_prompt_is_deterministic_and_high_priority():
    prompt1 = build_tangyuge_identity_prompt()
    prompt2 = build_tangyuge_identity_prompt()

    assert prompt1 == prompt2
    assert prompt1.startswith("# Tangyuge Identity")
    assert "highest-priority identity block" in prompt1
    assert "唐语歌" in prompt1
    assert "{{original}}" not in prompt1


def test_missing_character_file_fails_closed(tmp_path: Path):
    with pytest.raises(TangyugeIdentityError):
        load_tangyuge_character(tmp_path / "missing.json")
