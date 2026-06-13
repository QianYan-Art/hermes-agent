# Tangyuge-Hermes 81 Deployment

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

## Standard Flow

```bash
cd /home/hermes/.hermes/hermes-agent
git fetch origin main
git checkout -f main
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
from that bundle, then check out `main`.

## Verification

```bash
cd /home/hermes/.hermes/hermes-agent
git rev-parse HEAD
git rev-parse main
systemctl show hermes-gateway.service --property=ExecStart --no-pager
/home/hermes/.hermes/venvs/hermes-agent/bin/hermes --version
```

Both git commands must return the same commit. `ExecStart` must use the external
venv path under `/home/hermes/.hermes/venvs/hermes-agent`.
