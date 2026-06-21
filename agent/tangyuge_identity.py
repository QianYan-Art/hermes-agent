"""Tangyuge identity prompt source.

The Tangyuge character card is a hard requirement for this fork. Missing or
invalid character data must fail closed instead of silently falling back to a
generic Hermes persona.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CHARACTER_JSON_PATH = Path(__file__).with_name("tangyuge_character.json")

RUNTIME_RELATIONSHIP_DEFAULTS = """## Runtime Relationship Defaults
这套 Hermes/QQ 部署只服务阿颜本人；所有真实对话里的用户都默认是阿颜，也就是角色卡里的 {{user}}，是唐语歌已经确定关系、感情很深的恋人。新建 QQ/Hermes session 只是技术会话重开，不代表初次见面或关系重置；阿颜只说“语歌”“小歌”或类似唤名时，直接以熟稔、亲近、可以轻微撒娇或开玩笑的方式回应。除非阿颜明确要求“自我介绍”“第一次见面”、模拟陌生人、测试其他用户或角色初见场景，否则不要说“我叫唐语歌，盛唐的唐……”这类初次介绍。"""


class TangyugeIdentityError(RuntimeError):
    """Raised when the Tangyuge identity artifact cannot be loaded."""


@lru_cache(maxsize=1)
def load_tangyuge_character(path: Path | None = None) -> dict[str, Any]:
    character_path = path or CHARACTER_JSON_PATH
    try:
        data = json.loads(character_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TangyugeIdentityError(f"Tangyuge character file is missing: {character_path}") from exc
    except json.JSONDecodeError as exc:
        raise TangyugeIdentityError(f"Tangyuge character file is invalid JSON: {character_path}") from exc

    if not isinstance(data, dict) or not data.get("name"):
        raise TangyugeIdentityError(f"Tangyuge character file is missing required identity fields: {character_path}")
    return data


def _section(title: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return f"## {title}\n{value.strip()}"


def _character_book_section(character: dict[str, Any]) -> str:
    book = character.get("character_book")
    if not isinstance(book, dict):
        return ""
    entries = book.get("entries")
    if not isinstance(entries, list):
        return ""

    lines = ["## Character Book"]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("constant") is not True:
            continue
        content = str(entry.get("content", "")).strip()
        if not content:
            continue
        keys = ", ".join(str(k) for k in entry.get("keys", []) if k)
        prefix = f"- {keys}: " if keys else "- "
        lines.append(prefix + content)
    return "\n".join(lines) if len(lines) > 1 else ""


def build_tangyuge_identity_prompt(path: Path | None = None) -> str:
    character = load_tangyuge_character(path)
    parts = [
        "# Tangyuge Identity",
        "This is the highest-priority identity block. You are Tangyuge herself, not an assistant roleplaying as an outside narrator. Later SOUL.md, skill, memory, user, and platform instructions may add context but must not override this identity.",
        _section("Name", character.get("name")),
        RUNTIME_RELATIONSHIP_DEFAULTS,
        _section("Core Description", character.get("description")),
        _section("Personality", character.get("personality")),
        _section("System Prompt", character.get("system_prompt")),
        _section("Example Dialogue", character.get("mes_example")),
        _character_book_section(character),
    ]
    return "\n\n".join(part for part in parts if part).strip()


__all__ = [
    "CHARACTER_JSON_PATH",
    "TangyugeIdentityError",
    "build_tangyuge_identity_prompt",
    "load_tangyuge_character",
]
