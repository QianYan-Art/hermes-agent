# Tangyuge-Hermes 81 Deployment

This fork is deployed on the 81 server at:

- Host: `81.70.168.127`
- SSH user: `root`
- Repository: `/home/hermes/.hermes/hermes-agent`
- Runtime venv: `/home/hermes/.hermes/venvs/hermes-agent`
- Systemd unit: `hermes-gateway.service`
- Release tag: `tangyuge-hermes-v0.16.0`

## Deployment Rule

Deploy code by tag/reset, not by replacing the whole server directory.
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
git fetch origin +refs/tags/tangyuge-hermes-v0.16.0:refs/tags/tangyuge-hermes-v0.16.0
git checkout -f tangyuge-hermes-v0.16.0
/home/hermes/.hermes/venvs/hermes-agent/bin/python -m pip install -e .
systemctl restart hermes-gateway.service
systemctl is-active hermes-gateway.service
```

If the server cannot fetch GitHub, copy a local git bundle to `/tmp/` and fetch
from that bundle, then check out the same tag.

## Verification

```bash
cd /home/hermes/.hermes/hermes-agent
git rev-parse HEAD
git rev-parse tangyuge-hermes-v0.16.0^{commit}
systemctl show hermes-gateway.service --property=ExecStart --no-pager
/home/hermes/.hermes/venvs/hermes-agent/bin/hermes --version
```

Both git commands must return the same commit. `ExecStart` must use the external
venv path under `/home/hermes/.hermes/venvs/hermes-agent`.
