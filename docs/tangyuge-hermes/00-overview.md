# Tangyuge-Hermes Overview

常用叫法："总览"、"项目总览"、"整体情况"、"二开项目"、
"tangyuge-hermes 是什么"、"文档目录"。

`tangyuge-hermes` is the 81 server QQBot-focused fork of Hermes Agent. The project baseline is frozen at Hermes Agent v0.16.0 (2026-06-05) and the 2026-06-12 81-server snapshot; this fork does not track upstream feature churn after that point.

The Python package name and CLI command remain `hermes` for compatibility with existing service files, scripts, imports, and local operator habits. Public-facing project documentation and release notes use the `tangyuge-hermes` name.

## Runtime Scope

This fork keeps the 81 server's daily QQBot workflow as the primary supported runtime:

- QQBot gateway operation.
- QianYan server patches already present in the snapshot.
- Tangyuge identity as the highest-priority model identity.
- Runtime `SOUL.md` as style overlay only; legacy default SOUL identity text is
  normalized away by the loader and should not exist in the active 81 file.
- The retained operational skills and RTK plugin path required by the server.

Non-server surfaces such as desktop apps, website/web UI, bootstrap installers, dashboard GUI, and TUI shells are outside the target runtime unless a later mission issue explicitly keeps a compatibility shim.

## Runtime Data Boundary

Server runtime data must stay outside the repository and must not be overwritten by deployment:

- `/home/hermes/.hermes/.env`
- `/home/hermes/.hermes/config.yaml`
- `/home/hermes/.hermes/memories/`
- `/home/hermes/.hermes/emojis/`
- `/home/hermes/.hermes/sessions/`
- `/home/hermes/.hermes/audio_cache/`
- `/home/hermes/.hermes/image_cache/`
- `/home/hermes/.hermes/cache/`
- `/home/hermes/.hermes/state.db`
- `/home/hermes/.hermes/pairing/`
- `/home/hermes/.hermes/auth.json`

Deployments should use the `main` branch and `git reset`/forced checkout for code updates. The recommended virtual environment path is outside the repo at `/home/hermes/.hermes/venvs/hermes-agent` so dependency installation does not mix with runtime state or tracked source files.

On the current 81 host, active generated-image and TTS files still land in the
top-level `image_cache/` and `audio_cache/` directories because those legacy
paths already exist. `cache/documents/` stays active for document uploads and
the current QQ inbound video temp path.

## Documentation Layout

The bot-facing documentation source is this repository directory:

- `docs/tangyuge-hermes/00-overview.md`
- `docs/tangyuge-hermes/01-deployment-81.md`
- `docs/tangyuge-hermes/02-trim-plan.md`
- `docs/tangyuge-hermes/03-identity-prompt.md`
- `docs/tangyuge-hermes/04-built-in-skills.md`
- `docs/tangyuge-hermes/05-patches-and-rtk.md`
- `docs/tangyuge-hermes/06-upgrade-freeze.md`
- `docs/tangyuge-hermes/07-server-operations.md`
- `docs/tangyuge-hermes/08-mail-vps.md`

`hermes-md-locator` points to these repo docs only. The local KBase directory
keeps human record notes and is not a server sync source. The 81 server should
not maintain separate home-directory lookup document copies.

## Documentation And Memory Rules

When project behavior changes, keep these sources aligned:

- Update repo docs under `docs/tangyuge-hermes/` first. These are the bot-facing
  source of truth and must be reachable through `hermes-md-locator`.
- When docs or README add/remove topics, aliases, or current-state facts, update
  `skills_builtin/hermes-md-locator/SKILL.md` in the same change so the bot can
  locate the new content from natural user phrasing.
- Update Windows KBase records only as local operator notes. Do not sync KBase
  records to the server and do not make the bot depend on them for lookup.
- Update durable NowledgeMem state by refining the existing Tangyuge-Hermes
  current-state memory when possible. Prefer merging/superseding stale duplicate
  memories over creating new memory entries.
- When prompt, SOUL, identity, or roleplay behavior changes, verify both the
  always-on role card and `tangyuge-roleplay` skill boundary: the role card
  defines identity; the skill only adds style, relationship, and topic
  resources.
- Do not keep old bundles, temporary deployment archives, historical home-level
  docs, or obsolete server backups after successful deployment verification.

## Baseline Verification

Before release or deployment, verify the current commit and test evidence:

```bash
git rev-parse --short HEAD
python scripts/run_trimmed_tests.py
```

The `main` branch is the validated deployment line for the 81 server. The
trimmed verification profile lives in `tests/trimmed_manifest.py`; unscoped
`python -m pytest` is not the release baseline because it still discovers
upstream residual tests for removed platforms and tools.
