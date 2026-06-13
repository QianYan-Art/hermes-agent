# Server Operations

This is the bot-facing operations reference for Tangyuge-Hermes on the 81
server. It replaces the old `/home/hermes/HERMES_*.md` lookup documents.

## Source Of Truth

- Code: `/home/hermes/.hermes/hermes-agent`
- Runtime home: `/home/hermes/.hermes`
- Virtual environment: `/home/hermes/.hermes/venvs/hermes-agent`
- Service: `hermes-gateway.service`
- Service command: `/home/hermes/.hermes/venvs/hermes-agent/bin/hermes gateway run`
- Repo docs: `/home/hermes/.hermes/hermes-agent/docs/tangyuge-hermes/`

Do not keep separate `/home/hermes/HERMES_*.md` or
`/home/hermes/TANGYUGE_HERMES_*.md` docs. `hermes-md-locator` should route
project, server, maintenance, and mail-documentation questions to repo docs.

## Current Runtime Shape

Retained toolsets:

- `browser`
- `clarify`
- `cronjob`
- `delegation`
- `file`
- `image_gen`
- `memory`
- `messaging`
- `skills`
- `terminal`
- `todo`
- `tts`
- `vision`
- `web`

Enabled built-in skills:

- `grill-me`
- `grok-search`
- `hermes-md-locator`
- `mail-vps-ops`
- `paper-translation-to-docx`
- `tangyuge-roleplay`

Supported platform surface is narrowed to QQBot, API server, CLI, and cron.
Removed command/platform/tool surfaces should stay removed unless a later
mission explicitly reintroduces them.

## Runtime Data Boundary

Never overwrite or commit server runtime data:

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

The repo is deployed from `main`. Runtime state is server-local.

## Standard Checks

Use these before and after deployment:

```bash
cd /home/hermes/.hermes/hermes-agent
git rev-parse --short HEAD
git rev-parse --short main
systemctl is-active hermes-gateway.service
systemctl show hermes-gateway.service -p ExecStart --value
HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes \
  /home/hermes/.hermes/venvs/hermes-agent/bin/python -m hermes_cli.main skills list --enabled-only
```

Expected service state is `active`. Expected `ExecStart` uses the external venv
path, not a repo-local `venv`.

## Deployment Flow

Preferred flow:

```bash
cd /home/hermes/.hermes/hermes-agent
git fetch origin main
git checkout -f main
/home/hermes/.hermes/venvs/hermes-agent/bin/python -m pip install -e .
systemctl restart hermes-gateway.service
```

If GitHub fetch fails from the 81 server, use a local git bundle and fetch it
on the server, then checkout `main`.

## Documentation Rule

For bot-readable documentation, update repo docs under
`docs/tangyuge-hermes/` and redeploy. KBase records on the Windows machine are
operator notes only and are not synced to the server.
