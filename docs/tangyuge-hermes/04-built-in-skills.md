# Built-In Skills

常用叫法："内置skills"、"skills列表"、"有哪些skill"、"locator技能"、
"mail-vps-ops"、"技能怎么内置"。

Tangyuge-Hermes retains exactly six built-in skills for the 81 server workflow:

- `grill-me`
- `grok-search`
- `hermes-md-locator`
- `mail-vps-ops`
- `paper-translation-to-docx`
- `tangyuge-roleplay`

These live under `skills_builtin/` and are loaded before local/external skill
directories so clean installs can discover them without copying server-local
skill folders into the repo.

## Skill Boundaries

- `tangyuge-roleplay` is style/reference material only; the core identity comes
  from `agent/tangyuge_identity.py`. Its resources must stay below the core
  identity, avoid re-injecting the role card, and avoid introducing original
  named characters into the current conversation. Its Topic Routing maps
  natural cues such as 初雪, 文学社, 读书会, 亲爱的, 甜品, 奶茶, 便当, 荷包, and
  现金 to the appropriate resource documents.
- `hermes-md-locator` is the dynamic documentation entrypoint. Keep its
  description, route table, combination routes, and trigger phrases aligned with
  current `docs/tangyuge-hermes/` and README content whenever bot-facing docs
  change.
- `grok-search` documents environment-variable based configuration only. Real
  secrets must remain in runtime environment or server-local config.
- Sub-agents default to no memory/skill mutation capability.

## Verification

```bash
python -m hermes_cli.main skills list --enabled-only
```

The enabled list should show the six retained skills and no broad upstream skill
catalog.
