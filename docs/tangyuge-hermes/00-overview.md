# Tangyuge-Hermes Overview

`tangyuge-hermes` is the 81 server QQBot-focused fork of Hermes Agent. The project baseline is frozen at Hermes Agent v0.16.0 (2026-06-05) and the server snapshot tag `server-snapshot-2026-06-12`; this fork does not track upstream feature churn after that point.

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

Deployments should use git tags and `git reset` for code updates. The recommended virtual environment path is outside the repo at `/home/hermes/.hermes/venvs/hermes-agent` so dependency installation does not mix with runtime state or tracked source files.

## Baseline Verification

Before release or deployment, verify the branch and tag relationship:

```bash
git merge-base --is-ancestor server-snapshot-2026-06-12 HEAD
git rev-parse --short server-snapshot-2026-06-12^{commit}
git rev-parse --short HEAD
```

The first command must succeed. Release tags for this fork should point at validated `tangyuge-hermes` commits and should be deployed by tag on the 81 server.
