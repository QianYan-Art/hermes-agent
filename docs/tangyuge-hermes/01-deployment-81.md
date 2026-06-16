# Tangyuge-Hermes 81 Deployment

常用叫法："部署文档"、"81部署"、"81服务器部署"、"服务器怎么部署"、
"靠什么部署"、"main分支部署"、"服务命令"、"旧版本还保留吗"。

This fork is deployed on the 81 server at:

- Host: `81.70.168.127`
- SSH user: `root`
- Repository: `/home/hermes/.hermes/hermes-agent`
- Runtime venv: `/home/hermes/.hermes/venvs/hermes-agent`
- Systemd unit: `hermes-gateway.service`
- Release branch: `main`

## Deployment Rule

Deploy code by `main` checkout/reset, not by replacing the whole server directory.
Runtime data under `/home/hermes/.hermes/` must not be copied into the repo or
overwritten by deploy:

- `.env`
- `config.yaml`
- `memories/`
- `emojis/`
- `sessions/`
- `audio_cache/`
- `image_cache/`
- `state.db`
- `pairing/`
- `auth.json`

`/home/hermes/.hermes/SOUL.md` is runtime-local but must remain a style overlay
only. It must not contain `You are Hermes Agent`, `created by Nous Research`, or
any other identity definition. Code also normalizes the old default SOUL identity
template at load time, but the deployed runtime file should still be kept clean.

## Sparse Server Checkout

The 81 server checkout is runtime-only. Keep tests and development-only files in
local/GitHub history, but exclude them from the server worktree with
sparse-checkout:

```bash
cd /home/hermes/.hermes/hermes-agent
git sparse-checkout init --no-cone
git sparse-checkout set --no-cone '/*' '!/tests/' '!/.github/' '!/.plans/' '!/plans/' '!/infographic/' '!/datagen-config-examples/' '!/docker/'
```

Excluded server paths:

- `tests/`
- `.github/`
- `.plans/`
- `plans/`
- `infographic/`
- `datagen-config-examples/`
- `docker/`

Do not interpret these sparse omissions as source deletion. Local and GitHub
`main` remain the full review/test baseline; only the server checkout is slim.

## Standard Flow

```bash
cd /home/hermes/.hermes/hermes-agent
git fetch origin main
git sparse-checkout init --no-cone
git sparse-checkout set --no-cone '/*' '!/tests/' '!/.github/' '!/.plans/' '!/plans/' '!/infographic/' '!/datagen-config-examples/' '!/docker/'
git pull --ff-only origin main
/home/hermes/.hermes/venvs/hermes-agent/bin/python -m pip install -e .
systemctl restart hermes-gateway.service
systemctl is-active hermes-gateway.service
```

Chat-side operator restart:

- Send `/restart` from an allowed/admin QQ DM to trigger the built-in graceful
  gateway restart.
- Exact DM plaintext `restart gateway` is also routed to `/restart`.
- This is not a general shell escape; it is the gateway restart handler.

If the server cannot fetch GitHub, copy a local git bundle to `/tmp/` and fetch
from that bundle, then fast-forward `main`.

## Verification

```bash
cd /home/hermes/.hermes/hermes-agent
git rev-parse HEAD
git rev-parse main
git status --short
git sparse-checkout list
systemctl show hermes-gateway.service --property=ExecStart --no-pager
/home/hermes/.hermes/venvs/hermes-agent/bin/hermes --version
grep -E 'You are Hermes Agent|created by Nous Research' /home/hermes/.hermes/SOUL.md || true
```

Both git commands must return the same commit. `ExecStart` must use the external
venv path under `/home/hermes/.hermes/venvs/hermes-agent`. The grep command
should print nothing.
