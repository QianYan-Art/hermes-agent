#!/usr/bin/env python3
"""Extract a runtime-safe Tangyuge identity JSON from a SillyTavern PNG card."""

from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import zlib
from datetime import date
from pathlib import Path
from typing import Any


PROMPT_EXCLUDED_FIELDS = {
    "first_mes",
    "alternate_greetings",
    "creator_notes",
    "post_history_instructions",
    "tags",
    "creator",
    "extensions",
}

DETAILS_BLOCK_RE = re.compile(r"\n*<details\b.*?</details>\s*", re.IGNORECASE | re.DOTALL)


def _png_text_chunks(path: Path) -> list[tuple[str, bytes]]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG file")

    pos = 8
    chunks: list[tuple[str, bytes]] = []
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError(f"{path} has a truncated PNG chunk header")
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8].decode("latin1")
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length

        if chunk_type == "tEXt":
            key, value = chunk_data.split(b"\x00", 1)
            chunks.append((key.decode("utf-8", "replace"), value))
        elif chunk_type == "zTXt":
            key, rest = chunk_data.split(b"\x00", 1)
            if rest[:1] != b"\x00":
                raise ValueError(f"{path} uses unsupported zTXt compression method")
            chunks.append((key.decode("utf-8", "replace"), zlib.decompress(rest[1:])))
        elif chunk_type == "iTXt":
            parts = chunk_data.split(b"\x00", 5)
            if len(parts) != 6:
                continue
            key = parts[0].decode("utf-8", "replace")
            compressed = parts[1] == b"\x01"
            text = zlib.decompress(parts[5]) if compressed else parts[5]
            chunks.append((key, text))

    return chunks


def load_sillytavern_card(path: Path) -> dict[str, Any]:
    """Load Character Card JSON embedded in a PNG text chunk."""
    for key, raw_value in _png_text_chunks(path):
        values = [raw_value.decode("utf-8")]
        if key == "chara":
            try:
                values.append(base64.b64decode(values[0]).decode("utf-8"))
            except Exception:
                pass
        for value in values:
            try:
                card = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(card, dict) and isinstance(card.get("data", card), dict):
                return card
    raise ValueError(f"{path} does not contain a supported SillyTavern card")


def _compact_character_book(book: Any) -> dict[str, Any] | None:
    if not isinstance(book, dict):
        return None
    result: dict[str, Any] = {}
    for key in ("name", "description", "scan_depth", "token_budget", "recursive_scanning"):
        if key in book:
            result[key] = book[key]

    entries = []
    for entry in book.get("entries", []) or []:
        if not isinstance(entry, dict) or not entry.get("enabled", True):
            continue
        entries.append(
            {
                "keys": entry.get("keys", []),
                "content": entry.get("content", ""),
                "constant": bool(entry.get("constant", False)),
                "position": entry.get("position", ""),
                "insertion_order": entry.get("insertion_order", 0),
            }
        )
    if entries:
        result["entries"] = entries
    return result or None


def _strip_html_panels(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return DETAILS_BLOCK_RE.sub("\n", value).strip()


def build_runtime_identity(card: dict[str, Any], source: Path, extract_date: str | None = None) -> dict[str, Any]:
    data = card.get("data", card)
    if not isinstance(data, dict):
        raise ValueError("card data must be an object")

    runtime: dict[str, Any] = {
        "provenance": {
            "spec": card.get("spec", ""),
            "spec_version": card.get("spec_version", ""),
            "source_filename": source.name,
            "extract_date": extract_date or date.today().isoformat(),
        },
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "personality": data.get("personality", ""),
        "scenario": data.get("scenario", ""),
        "mes_example": _strip_html_panels(data.get("mes_example", "")),
        "system_prompt": _strip_html_panels((data.get("system_prompt", "") or "").replace("{{original}}", "")),
        "character_version": data.get("character_version", ""),
    }
    book = _compact_character_book(data.get("character_book"))
    if book:
        runtime["character_book"] = book

    for field in PROMPT_EXCLUDED_FIELDS:
        runtime.pop(field, None)
    return runtime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    card = load_sillytavern_card(args.source)
    runtime = build_runtime_identity(card, args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(runtime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
