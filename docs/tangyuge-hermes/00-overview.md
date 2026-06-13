# Tangyuge-Hermes Overview

Common user aliases for this document: "总览", "项目总览", "整体情况",
"二开项目", "tangyuge-hermes 是什么", "文档目录".

`tangyuge-hermes` is the 81 server QQBot-focused fork of Hermes Agent. The project baseline is frozen at Hermes Agent v0.16.0 (2026-06-05) and the 2026-06-12 81-server snapshot; this fork does not track upstream feature churn after that point.

The Python package name and CLI command remain `hermes` for compatibility with existing service files, scripts, imports, and local operator habits. Public-facing project documentation and release notes use the `tangyuge-hermes` name.

## Runtime Scope

This fork keeps the 81 server's daily QQBot workflow as the primary supported runtime:

- QQBot gateway operation.
- QianYan server patches already present in the snapshot.
- Tangyuge identity as the highest-priority model identity.
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
- `/home/hermes/.hermes/state.db`
- `/home/hermes/.hermes/pairing/`
- `/home/hermes/.hermes/auth.json`

Deployments should use the `main` branch and `git reset`/forced checkout for code updates. The recommended virtual environment path is outside the repo at `/home/hermes/.hermes/venvs/hermes-agent` so dependency installation does not mix with runtime state or tracked source files.

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
not maintain separate `/home/hermes/HERMES_*.md` or
`/home/hermes/TANGYUGE_HERMES_*.md` copies.

## Baseline Verification

Before release or deployment, verify the current commit and test evidence:

```bash
git rev-parse --short HEAD
python -m compileall -q agent gateway tools skills_builtin scripts tests
```

The `main` branch is the validated deployment line for the 81 server.
