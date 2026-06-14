# Server Operations

This is the bot-facing operations reference for Tangyuge-Hermes on the 81
server. It replaces the old home-directory lookup documents.

## Source Of Truth

常用叫法："维护手册"、"全局状态"、"服务器全局状态"、"当前状态"、
"重启网关命令"、"自动清理session任务"、"session清理timer"。

- Code: `/home/hermes/.hermes/hermes-agent`
- Runtime home: `/home/hermes/.hermes`
- Virtual environment: `/home/hermes/.hermes/venvs/hermes-agent`
- Service: `hermes-gateway.service`
- Service command: `/home/hermes/.hermes/venvs/hermes-agent/bin/hermes gateway run`
- Repo docs: `/home/hermes/.hermes/hermes-agent/docs/tangyuge-hermes/`

Do not keep separate home-directory lookup docs. `hermes-md-locator` should
route project, server, maintenance, and mail-documentation questions to repo
docs.

## Current Runtime Shape

Default model provider:

- Provider slug: `deepseek-direct`
- Display name: `DeepSeek`
- Base URL: `https://api.deepseek.com/v1`
- Default model: `deepseek-chat`
- Key env: `TANGYUGE_DEEPSEEK_API_KEY`
- Do not use `DEEPSEEK_API_KEY` on the 81 deployment; the built-in DeepSeek
  provider can auto-discover that env var and duplicate the custom DeepSeek row
  in model selection flows.
- Built-in API-key provider env discovery is disabled by default. Do not set
  `HERMES_BUILTIN_ENV_PROVIDER_DISCOVERY=1` on the 81 deployment unless the
  intent is to restore legacy built-in provider auto-listing from env vars.

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

## Session Cleanup Timer

The 81 server keeps a systemd timer for old session transcript cleanup:

- Timer: `hermes-session-cleanup.timer`
- Service: `hermes-session-cleanup.service`
- Script: `/usr/local/sbin/hermes-session-cleanup`
- Schedule: `OnBootSec=15m` and `OnUnitInactiveSec=10d`
- Policy: `/usr/local/sbin/hermes-session-cleanup --days 10 --delete`
- Scope: deletes old non-active files under `/home/hermes/.hermes/sessions`
- Protection: session IDs still referenced by
  `/home/hermes/.hermes/sessions/sessions.json` are not deleted.
- Unit documentation: this file,
  `/home/hermes/.hermes/hermes-agent/docs/tangyuge-hermes/07-server-operations.md`

Check status:

```bash
systemctl is-enabled hermes-session-cleanup.timer
systemctl is-active hermes-session-cleanup.timer
systemctl list-timers hermes-session-cleanup.timer --no-pager
systemctl cat hermes-session-cleanup.service
```

## Deployment Flow

Preferred flow:

```bash
cd /home/hermes/.hermes/hermes-agent
git fetch origin main
git checkout -f main
/home/hermes/.hermes/venvs/hermes-agent/bin/python -m pip install -e .
systemctl restart hermes-gateway.service
```

Chat-side restart:

- `/restart` is available to allowed/admin chat users and runs the gateway's
  built-in graceful restart handler.
- In DM only, exact plaintext `restart gateway` is treated as `/restart`.
- This command does not grant arbitrary shell access to the bot.

Chinese operator phrasing:

- If the user says "去维护手册里查重启网关命令", the answer is this section.
- QQ/DM 重启网关命令：`/restart`
- QQ/DM 英文快捷句：`restart gateway`
- SSH 运维重启命令：`systemctl restart hermes-gateway.service`

If GitHub fetch fails from the 81 server, use a local git bundle and fetch it
on the server, then checkout `main`.

## Documentation Rule

For bot-readable documentation, update repo docs under
`docs/tangyuge-hermes/` and redeploy. KBase records on the Windows machine are
operator notes only and are not synced to the server.

## Cleanup Rule

After deployment or documentation changes:

- Keep the local repo, WSL view, GitHub `main`, and server checkout aligned.
- Remove local and server `.bundle` deployment archives after successful use.
- Keep server runtime data under `/home/hermes/.hermes/` intact; never replace
  `.env`, `config.yaml`, memories, sessions, media caches, or user documents.
- Remove obsolete home-directory lookup docs and old code backups when they are
  no longer referenced.
- For NowledgeMem, update the existing Tangyuge-Hermes current-state memory and
  merge/supersede duplicate old memories instead of creating parallel entries.
