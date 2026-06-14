# Tangyuge-Hermes

Tangyuge-Hermes is QianYan's second-development fork of Hermes Agent for the
81 server QQBot deployment. It keeps the upstream Python package name and CLI
command `hermes` only for compatibility with existing imports, service files,
operator scripts, and runtime paths.

This repository is not an upstream-tracking Hermes Agent distribution. The
baseline is frozen at Hermes Agent v0.16.0 and the server snapshot
the 2026-06-12 81-server snapshot; later work should treat this fork as its
own project unless a deliberate upstream merge is planned and tested.

## Runtime Shape

- Server: `81.70.168.127`
- Runtime user/home: `/home/hermes`
- Repo path: `/home/hermes/.hermes/hermes-agent`
- Runtime home: `/home/hermes/.hermes`
- Virtualenv: `/home/hermes/.hermes/venvs/hermes-agent`
- Systemd unit: `hermes-gateway.service`
- Service command: `/home/hermes/.hermes/venvs/hermes-agent/bin/hermes gateway run`

Runtime data stays outside the repo. Do not overwrite these server-local paths
during deploys:

- `/home/hermes/.hermes/.env`
- `/home/hermes/.hermes/config.yaml`
- `/home/hermes/.hermes/memories/`
- `/home/hermes/.hermes/sessions/`
- `/home/hermes/.hermes/emojis/`
- `/home/hermes/.hermes/audio_cache/`
- `/home/hermes/.hermes/image_cache/`
- `/home/hermes/.hermes/state.db`
- `/home/hermes/.hermes/pairing/`
- `/home/hermes/.hermes/auth.json`

## Core Fork Behavior

- Tangyuge identity is a first-class runtime identity, not a prompt pasted in by
  operators. The character card is extracted into `agent/tangyuge_character.json`,
  rendered by `agent/tangyuge_identity.py`, and injected first from
  `agent/system_prompt.py`.
- `/new` and `/reset` are distinct gateway commands. `/new` starts a fresh
  session, returns model settings to global defaults, and deletes the previous
  session DB row/transcript. `/reset` starts a fresh session while preserving
  the current model/provider/reasoning config and the old session record.
- `/restart` is exposed to allowed/admin chat operators. In DM, exact plaintext
  such as `restart gateway` is also routed to `/restart`. It uses the gateway's
  built-in graceful restart handler, not arbitrary shell execution.
- `/status` and `/view` stay available while an agent is running.
- Automatic memory and skill-review loops are disabled on the Tangyuge Codex
  runtime path. Explicit memory/tool actions remain available.
- QianYan provider/model routing patches, auxiliary model behavior, Tavily
  multi-key failover, HYBGZS image backend behavior, mail VPS operation,
  `hermes-md-locator`, and Tangyuge roleplay references are built-in repo
  behavior, not external patch files to replay.
- MiniMax M3 media routing is built in for QQBot: images can remain on the
  configured auxiliary vision path, while supported QQ videos are attached to
  the MiniMax Anthropic-compatible request as native video blocks within a
  45 MiB per-file and per-turn inline budget.
- Child-agent tool access is constrained: leaf subagents cannot call
  `delegate_task`, `clarify`, `memory`, `send_message`, or `execute_code`;
  orchestrator subagents may delegate within configured depth but still cannot
  call `clarify`, `memory`, `send_message`, or `execute_code`.

## Bot-Facing Documentation

Bot-readable project documentation lives only under `docs/tangyuge-hermes/`.
`skills_builtin/hermes-md-locator/SKILL.md` routes project questions to these
repo docs.

- `docs/tangyuge-hermes/00-overview.md`
- `docs/tangyuge-hermes/01-deployment-81.md`
- `docs/tangyuge-hermes/02-trim-plan.md`
- `docs/tangyuge-hermes/03-identity-prompt.md`
- `docs/tangyuge-hermes/04-built-in-skills.md`
- `docs/tangyuge-hermes/05-patches-and-rtk.md`
- `docs/tangyuge-hermes/06-upgrade-freeze.md`
- `docs/tangyuge-hermes/07-server-operations.md`
- `docs/tangyuge-hermes/08-mail-vps.md`

The Windows KBase directory keeps human operator notes only. It is not a server
sync source and should not be used by the bot for lookup. The 81 server should
not keep separate home-directory lookup document copies.

## Deployment Rule

Deploy the repo by Git commit from `main` into the existing server checkout. Do
not copy over the whole `/home/hermes/.hermes` runtime tree.

Standard server flow:

```bash
cd /home/hermes/.hermes/hermes-agent
git fetch origin main
git checkout -f main
/home/hermes/.hermes/venvs/hermes-agent/bin/python -m pip install -e .
systemctl restart hermes-gateway.service
systemctl is-active hermes-gateway.service
```

From QQ/DM, an allowed admin operator can also send `/restart` to restart the
gateway through the built-in graceful restart path. The plaintext shortcut
`restart gateway` is intentionally DM-only.

If the server cannot fetch GitHub, create a local git bundle, copy it to
`/tmp/`, fetch from that bundle, then check out `main`.

## Verification

Before release or deploy:

```bash
python -m compileall -q agent gateway tools skills_builtin scripts tests
python -m pytest \
  tests/gateway/test_session_model_reset.py \
  tests/gateway/test_session_boundary_hooks.py \
  tests/gateway/test_command_bypass_active_session.py \
  tests/agent/test_tangyuge_identity.py \
  tests/agent/test_system_prompt.py \
  tests/tools/test_tangyuge_builtin_skills.py \
  tests/hermes_cli/test_tools_config.py::test_configurable_toolsets_match_tangyuge_retained_scope \
  -q --timeout-method=thread
```

On the server:

```bash
cd /home/hermes/.hermes/hermes-agent
git rev-parse --short HEAD
systemctl is-active hermes-gateway.service
systemctl show hermes-gateway.service --property=ExecStart --no-pager
```

Expected service state: active, using
`/home/hermes/.hermes/venvs/hermes-agent/bin/hermes gateway run`.
