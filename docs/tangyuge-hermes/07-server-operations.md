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
- Server checkout mode: sparse-checkout runtime tree; tests and development
  artifacts stay in local/GitHub `main` but are excluded on the server.

Do not keep separate home-directory lookup docs. `hermes-md-locator` should
route project, server, maintenance, and mail-documentation questions to repo
docs.

## Current Runtime Shape

Default model provider:

- Provider slug: `minimax-cn`
- Display name: `MiniMax (China)`
- Base URL: `https://api.minimaxi.com/anthropic`
- Default model: `minimax-m3`
- Key env: `MINIMAX_CN_API_KEY`
- The old main-model custom providers `openrouter`, `siliconflow`,
  `deepseek-direct`, and `xiaomi-token-plan-cn` are not used on the 81 runtime.
  Auxiliary/vision, image generation, and TTS settings are separate and should
  not be removed when cleaning main model providers.
- `DEEPSEEK_API_KEY` may remain in `.env` as a fallback key, but the default
  main model does not use it.
- `prompt_caching.cache_ttl` is `5m`; MiniMax prompt cache uses
  Anthropic-compatible `cache_control` markers and 5-minute renewal semantics.
- `agent.image_input_mode` is `auto` and `auxiliary.vision.provider` points to
  `custom:ollama_vision`, so QQ images are summarized by the auxiliary vision
  backend instead of being sent directly to MiniMax M3.
- QQ videos are routed independently from images. For the default
  `minimax-cn` / `minimax-m3` runtime, cached videos are attached directly to
  the upstream Anthropic-compatible request as native `video` blocks when the
  local file is supported and small enough for inline base64. The inline budget
  is 45 MiB per file and 45 MiB total per turn. Unsupported, missing, or
  oversized videos remain visible by cached file path in the text prompt.
- Built-in API-key provider env discovery is disabled by default. Do not set
  `HERMES_BUILTIN_ENV_PROVIDER_DISCOVERY=1` on the 81 deployment unless the
  intent is to restore legacy built-in provider auto-listing from env vars.
- Bundled main-model provider discovery is allow-listed to `custom`,
  `deepseek`, and `minimax`. The expected provider registry is `custom`,
  `deepseek`, `minimax`, `minimax-cn`, and `minimax-oauth`.
- `/home/hermes/.hermes/SOUL.md` is a style-only overlay. It must not contain
  `You are Hermes Agent`, `created by Nous Research`, or any other identity
  definition. `agent/prompt_builder.py` normalizes the old default SOUL identity
  template at load time as a second safety net.
- Old runtime QQBot SOUL variants `SOUL_QQBOT_DM.md` and
  `SOUL_QQBOT_GROUP.md` were confirmed unused and removed. Current runtime
  prompt injection reads only `/home/hermes/.hermes/SOUL.md`.

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

Delegation runtime:

- `delegate_task(background=true)` is available for single-task async
  subagents. Results return to the same session through the gateway completion
  watcher.
- `delegation.max_async_children` defaults to `3`; new background subagent
  dispatches are rejected at capacity instead of queued.

Enabled built-in skills:

- `grill-me`
- `grok-search`
- `hermes-md-locator`
- `mail-vps-ops`
- `paper-translation-to-docx`
- `tangyuge-roleplay`

The server runtime directory `/home/hermes/.hermes/skills` should contain only
these six directories. Legacy upstream bundled skills such as `humanizer` and
`creative` have been removed from the runtime and ignored server checkout. The
guard file `/home/hermes/.hermes/.no-bundled-skills` prevents bootstrap code
from repopulating the upstream bundled skill catalog.

Supported platform surface is narrowed to QQBot, API server, CLI, and cron.
Removed command/platform/tool surfaces should stay removed unless a later
mission explicitly reintroduces them.

Removed top-level CLI commands fail closed with a Tangyuge-Hermes message:
`proxy`, `lsp`, `portal`, `kanban`, `curator`, `insights`, `claw`, `acp`,
`profile`, `honcho`, `dashboard`, `desktop`, and `gui`. The `memory` command is
narrowed to `status`, `off`, and `reset`.

README policy:

- `README.md` is the only repository README.
- Do not restore `README.zh-CN.md`; it previously carried upstream marketing
  and non-retained platform claims.

Plugin policy:

- The 81 runtime enables `rtk-rewrite` in `plugins.enabled`.
- Bundled plugin discovery is allow-listed to retained web/browser/image/RTK
  surfaces: `browser/browser_use`, `browser/browserbase`,
  `browser/firecrawl`, `web/exa`, `web/firecrawl`, `web/parallel`,
  `web/tavily`, `image_gen/openai`, `rtk-rewrite`, `disk-cleanup`, and
  `security-guidance`.
- Image generation uses the `image_gen/openai` provider against an
  OpenAI-compatible Images API endpoint. Keep endpoint URL in
  `image_gen.openai.base_url`; on the 81 runtime this is
  `https://suyuan.4071253.xyz/v1`. Keep the secret in
  `OPENAI_IMAGE_API_KEY`.
  The default API model sent to the endpoint is `gpt-image-2`. The visible
  `gpt-image-2-low`, `gpt-image-2-medium`, and `gpt-image-2-high` names are
  Hermes quality tiers; a non-tier `/auxmodel image <model>` value is treated
  as the actual Images API model sent to the endpoint. The `image_generate`
  tool can control `quality`, `num_images`, `output_format`, `background`,
  `moderation`, `output_compression`, `style`, and a non-tier `model` /
  explicit `api_model` override for text-to-image when the active provider
  supports those fields. It also supports image-to-image and local edits via
  `input_image`, `input_images`, `mask`, and `input_fidelity`; local paths,
  `file://` URLs, HTTP(S) URLs, and data URLs are accepted for source/mask
  images and are uploaded through the OpenAI SDK `images.edit` path.
  `output_compression` is valid only with `output_format=jpeg` or
  `output_format=webp`; the current bot-facing tool does not expose streaming
  partial image events.
- Bot image-generation requests should use `image_generate` directly. The tool
  returns cached local image paths with `media_tag` (`MEDIA:<path>`), and
  `gateway/run.py` auto-appends current-turn `image_generate` media tags when
  the final reply omits them. QQBot `send_message` media delivery uses the
  running QQBot adapter's native upload path; without that live adapter, the
  tool returns an explicit text-only REST-path error instead of dropping the
  attachment.
- QQBot daily expression supports two practical paths: Unicode emoji directly
  in text, or existing local sticker/image files under
  `/home/hermes/.hermes/emojis/` sent with `MEDIA:/absolute/path`. Bracketed
  placeholders such as `[害羞/比心]` are plain text on QQ and should not be used
  as a sticker-sending mechanism. The current QQBot adapter sends text,
  markdown, and native media files; it does not expose QQ native face-ID
  sending.
- QQBot approval buttons are active for dangerous command approvals. `允许一次`
  resolves the current pending approval only, `始终允许` persists the approval
  through the normal permanent allowlist path, and `拒绝` denies it. If a
  clicked button no longer has a pending approval to resolve, the bot replies
  that the authorization request has expired or already been handled.
- `hermes plugins list --plain` should list only `disk-cleanup`,
  `rtk-rewrite`, and `security-guidance`.
- Retained web/browser plugin shims may remain in the repo even though they are
  not standalone plugins, because retained `web` and `browser` toolsets import
  those provider modules directly.
- Non-retained model provider packages and non-OpenAI image provider packages
  are physically removed from the tracked source after retained-scope tests
  prove they are no longer referenced.

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
git status --short
git sparse-checkout list
systemctl is-active hermes-gateway.service
systemctl show hermes-gateway.service -p ExecStart --value
HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes \
  /home/hermes/.hermes/venvs/hermes-agent/bin/python -m hermes_cli.main plugins list --plain
git ls-files 'plugins/model-providers/*/plugin.yaml' | cut -d/ -f3 | sort -u
git ls-files 'plugins/image_gen/*/plugin.yaml' | cut -d/ -f3 | sort -u
HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes \
  /home/hermes/.hermes/venvs/hermes-agent/bin/python -m hermes_cli.main skills list --enabled-only
find /home/hermes/.hermes/skills -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
test -f /home/hermes/.hermes/.no-bundled-skills
find /home/hermes/.hermes -path '*/humanizer' -o -path '*/creative'
grep -E 'You are Hermes Agent|created by Nous Research' /home/hermes/.hermes/SOUL.md || true
```

Expected service state is `active`. Expected `ExecStart` uses the external venv
path, not a repo-local `venv`. The runtime skill list should be exactly the six
retained names, the `.no-bundled-skills` guard should exist, and the
`humanizer`/`creative` search should print nothing. The SOUL grep should print
nothing.

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
git sparse-checkout init --no-cone
git sparse-checkout set --no-cone '/*' '!/tests/' '!/.github/' '!/.plans/' '!/plans/' '!/infographic/' '!/datagen-config-examples/' '!/docker/'
git pull --ff-only origin main
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
- Keep `/home/hermes/.hermes/skills` aligned to the six retained skills and
  keep `/home/hermes/.hermes/.no-bundled-skills` in place. Preserve
  server-local secret files such as skill `.env` files when resyncing skill
  directories.
- Keep `/home/hermes/.hermes/SOUL.md` as a clean style overlay when prompt or
  identity code changes; do not restore old upstream default identity text.
- Remove obsolete home-directory lookup docs and old code backups when they are
  no longer referenced.
- For NowledgeMem, update the existing Tangyuge-Hermes current-state memory and
  merge/supersede duplicate old memories instead of creating parallel entries.
