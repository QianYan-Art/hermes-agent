# Server Operations

This is the bot-facing operations reference for Tangyuge-Hermes on the 81
server. It replaces the old home-directory lookup documents.

## Source Of Truth

常用叫法："维护手册"、"全局状态"、"服务器全局状态"、"当前状态"、
"重启网关命令"、"自动清理session任务"、"session清理timer"、
"/reasoning"、"推理强度"、"思考深度"、"max档位"、"会话与全局设置"。

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

QQBot gateway WebSocket support depends on the repo's core `aiohttp` pin. The
adapter imports `aiohttp` directly for `ClientSession`, WebSocket message types,
and proxy-aware `ws_connect`; a clean 81-style install must not depend on an
old server-local package left in the venv.

Removed top-level CLI commands fail closed with a Tangyuge-Hermes message:
`proxy`, `lsp`, `portal`, `kanban`, `curator`, `insights`, `claw`, `acp`,
`profile`, `honcho`, `dashboard`, `desktop`, and `gui`. The `memory` command is
narrowed to `status`, `off`, and `reset`.

README policy:

- `README.md` is the only repository README.
- Do not restore `README.zh-CN.md`; it previously carried upstream marketing
  and non-retained platform claims.

Repository security scanning is CI-only: `.github/workflows/osv-scanner.yml`
invokes `--config=osv-scanner.toml` for lockfile checks. That TOML file is
tracked with the checkout and is not server runtime data or a replacement for
upgrading a vulnerable retained dependency.

Plugin policy:

- The 81 runtime enables `rtk-rewrite` in `plugins.enabled`, and the active
  runtime plugin now resolves to the bundled `plugins/rtk-rewrite/` copy. The
  old `/home/hermes/.hermes/plugins/rtk-rewrite/` user override was removed
  after verifying it was byte-identical to the bundled plugin.
- The server binary `/home/hermes/.local/bin/rtk` was updated to `0.48.0` on
  2026-09-08. The Linux x86_64 musl archive was verified against SHA256
  `e4e650fa1677c0de2f6839a6040d7b17f312d32f163c402b75af70e9e5af1a91`;
  the installed file remains owned by `hermes:hermes` with mode `755`.
- 本次已验证实际 `pre_tool_call` 注册、命令改写、已有 `rtk` 前缀的幂等处理、
  不支持命令的透传和只读 Git 执行。成功改写返回码仍为 `3`，透传为 `1`，
  与现有插件兼容，不需要新增工具、恢复 user override 或运行 `rtk init`。
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
  Because this runtime explicitly sets `image_gen.provider: openai`,
  `image_generate` must appear in the model-visible tool list even if the
  provider has a transient credential or dependency problem. Those failures
  belong in the tool result as `auth_required`, `provider_not_registered`, or
  provider-specific errors; the model should still call `image_generate`
  directly instead of creating curl/Python/heredoc scripts.
- Bot image-generation requests should use `image_generate` directly. The tool
  returns cached local image paths with `media_tag` (`MEDIA:<path>`), and
  `gateway/run.py` auto-appends current-turn `image_generate` media tags when
  the final reply omits them. QQBot `send_message` media delivery uses the
  running QQBot adapter's native HTTP `POST` upload path; without that live
  adapter, the tool returns an explicit text-only REST-path error instead of
  dropping the attachment. Live adapter uploads and generic live-adapter
  `send()` calls are scheduled back onto the gateway-owned event loop so they
  do not fail with cross-loop `is bound to a different event loop` errors. QQ
  text/media sends can also use explicit event-based send context through
  `qq_event_id`, and QQ C2C sends can request `qq_is_wakeup`. On the current
  runtime, C2C native media still reuses the latest inbound message ID as a
  passive fallback only when no explicit `qq_event_id` / `qq_is_wakeup`
  context is present.
- When a QQ voice reply already contains tool-generated audio
  (`[[audio_as_voice]]` or audio `MEDIA:<path>`), the gateway sends that media
  through the normal media delivery path and does not generate a second
  runner-side auto-TTS reply.
- Platform config can set `typing_indicator: false` to disable the generic
  typing/thinking refresh loop for that platform while preserving reply
  delivery. The default remains `true`.
- QQ text/media send failures include both the human-readable `error` and a
  stable `SendResult.error_kind` category (`too_long`, `bad_format`,
  `forbidden`, `not_found`, `rate_limited`, `transient`, or `unknown`). The QQ
  WebSocket reader also raises immediately if the stored WebSocket is already
  closed, so reconnect/backoff logic handles that state instead of a tight
  read-loop retry.
- On the current 81 runtime, active generated-image and TTS files still land in
  `/home/hermes/.hermes/image_cache/` and `/home/hermes/.hermes/audio_cache/`
  because those legacy directories already exist on that host. The shared
  `/home/hermes/.hermes/cache/` tree remains active for `cache/documents/`,
  mail-skill caches, and the current QQ inbound video temp path. `video_cache/`
  exists in code but is not the current QQ inbound attachment path on 81.
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
- `/home/hermes/.hermes/cache/`
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

## 推理强度设置

- `/reasoning` 查看当前请求等级、作用域和思考显示设置。可选等级为
  `none/minimal/low/medium/high/xhigh/max`，`none` 表示关闭思考。
- QQ 中 `/reasoning max` 仅覆盖当前会话，下条消息生效，不写全局配置；
  `/reasoning max --global` 才保存到 `config.yaml` 的 `agent.reasoning_effort`。
- `/reasoning reset` 清除当前会话覆盖并重新使用全局配置；
  `show/hide/on/off` 仍控制思考内容显示，不是强度等级。
- CLI 的 `/reasoning max` 沿用直接保存全局配置的行为，与 QQ 默认作用域不同。
- 当前 MiniMax-M3 没有因新增枚举获得原生 `max` 能力。其现有手动预算路径将
  `max` 与 `xhigh` 都映射到 32000 token；支持原生 `max` 的 Anthropic 自适应
  路径使用 `output_config.effort=max`。具体效果以目标模型与接口能力为准，
  不要把命令接受枚举理解成所有模型都支持同名等级。
- 本次更新不更改 81 当前模型或推理配置，也不恢复已裁剪 provider。
  切换模型前先核对接口支持的等级；实现与兼容映射见 `05-patches-and-rtk.md`。

## Documentation Rule

For bot-readable documentation, update repo docs under
`docs/tangyuge-hermes/` and redeploy. KBase records on the Windows machine are
operator notes only and are not synced to the server.

KBase 只有阿颜明确授权后才能更新，改动只留本地，不提交、不推送、不运行博客同步。
NowledgeMem/nmem 与 Serena 指维护侧记忆，不是 Hermes runtime 的 `memories/`；
读取或核对记忆不等于获准写入，也不改变 Hermes 自身记忆工具的既有行为。
维护侧记忆的写入、合并、替换和删除均须阿颜明确授权，只保留长期稳定规则、
当前主状态和关键部署事实，不写临时日志、验证流水账或密钥内容。

## Cleanup Rule

After deployment or documentation changes:

- 三端基线只指本地 Git HEAD、GitHub `main` 和服务器 checkout HEAD；
  WSL 是本地工作区的访问视图，KBase 和服务器 runtime 数据不计入三端基线。
- Remove local and server `.bundle` deployment archives after successful use.
- `.doc-maintenance/` 是本地临时审阅目录，保持 Git 忽略并在完成后删除；
  不推送、不部署，不在 KBase 内生成。不要用 `git clean -fdX` 一刀切清理。
- Keep server runtime data under `/home/hermes/.hermes/` intact; never replace
  `.env`, `config.yaml`, memories, sessions, media caches, or user documents.
- Keep `/home/hermes/.hermes/skills` aligned to the six retained skills and
  keep `/home/hermes/.hermes/.no-bundled-skills` in place. Preserve
  server-local secret files such as skill `.env` files when resyncing skill
  directories.
- Keep `/home/hermes/.hermes/SOUL.md` as a clean style overlay when prompt or
  identity code changes; do not restore old upstream default identity text.
- 旧 home 文档、代码备份和 `.bak` 删除前，先核查引用、运行依赖及恢复价值，
  明确精确路径后再清理，不按文件后缀或年龄批量删除。
- 清理会话前的 SQLite 快照可能保存当前库已删除的历史数据；不能仅因文件旧、
  没有运行引用或现用数据库正常而判定冗余。无法证明没有恢复价值时保留。
- SSH 备份（例如 `known_hosts.old`）只有在确证内容冗余、没有独立恢复价值后
  才可清理；不得连带删除或改写现用 SSH 文件。
- 获得记忆更新授权后，优先维护既有 Tangyuge-Hermes 当前状态主条目；
  不把过时快照当作当前状态，也不创建重复的平行条目。
