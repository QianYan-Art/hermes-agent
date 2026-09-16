# Tangyuge-Hermes

Tangyuge-Hermes is QianYan's second-development fork of Hermes Agent for the
81 server QQBot deployment. It keeps the upstream Python package name and CLI
command `hermes` only for compatibility with existing imports, service files,
operator scripts, and runtime paths.

This repository is not an upstream-tracking Hermes Agent distribution. The
baseline is frozen at Hermes Agent v0.16.0 and the server snapshot
from the 2026-06-12 81-server snapshot; later work should treat this fork as its
own project unless a deliberate upstream merge is planned and tested.

## Runtime Shape

- Server: `81.70.xx.xx`（公开仓库中脱敏；真实地址见本机授权范围内的配置，不回填此处）
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
- `/home/hermes/.hermes/cache/`
- `/home/hermes/.hermes/state.db`
- `/home/hermes/.hermes/pairing/`
- `/home/hermes/.hermes/auth.json`

On the current 81 runtime, active generated-image and TTS files still land in
`image_cache/` and `audio_cache/` because those legacy directories already
exist on that host. QQ 普通文件进入 `cache/documents/`，入站视频进入
`cache/videos/`，入站语音进入 `audio_cache/`，四类媒体分别清理。

## Core Fork Behavior

- Tangyuge identity is a first-class runtime identity, not a prompt pasted in by
  operators. The character card is extracted into `agent/tangyuge_character.json`,
  rendered by `agent/tangyuge_identity.py`, and injected first from
  `agent/system_prompt.py`.
- Tangyuge replies are natural QQ/Hermes chat replies, not role-card UI output.
  The role card and `tangyuge-roleplay` skill must not make normal replies add
  fixed UI blocks, numeric meters, relationship/mood tables, HTML folding
  blocks, or per-turn recap blocks unless the user explicitly asks for
  structured output in that turn.
- QQBot daily expression should use Unicode emoji directly in text or send
  existing sticker images from `/home/hermes/.hermes/emojis/` with
  `MEDIA:/absolute/path`. Bracketed placeholders such as `[害羞/比心]` are plain
  text on QQ and are not a sticker-sending mechanism.
- `SOUL.md` is a style overlay only. Legacy default SOUL files that still say
  `You are Hermes Agent` are normalized to the style-only overlay at load time,
  and the 81 runtime file must not redefine identity.
- `/new` and `/reset` are distinct gateway commands. `/new` starts a fresh
  session, returns model settings to global defaults, and deletes the previous
  session DB row/transcript. `/reset` starts a fresh session while preserving
  the current model/provider/reasoning config and the old session record. The
  gateway replies for these commands do not append random discovery tips.
- `/reasoning` 支持 `none/minimal/low/medium/high/xhigh/max`。QQ 中默认只修改
  当前会话，添加 `--global` 才写入全局配置；CLI 沿用直接保存行为。
  `max` 是否原生生效取决于所选模型与接口。当前默认模型 Kimi Code 只有
  `low/high/max` 三档，网关按 `minimal|low -> low`、`medium|high -> high`、
  `xhigh|max -> max` 映射。
- `/model` 与 `/context` 的作用域一致：不带 `--global` 只影响当前会话，
  包括上下文窗口——会话级 `/model` 不再把自动探测值写进全局
  `model.context_length`。`/context` 的单位是二进制（`k = 1024`、
  `m = 1024²`），不带单位的整数保持原值。模型切换无法解析窗口时保留
  显式配置；无配置时回落 `256000`（250K），来源与作用域在回显中区分。
- Kimi Code 请求使用 `Tangyuge-Hermes/<版本>` 标识和会话/任务级
  `prompt_cache_key`；缓存统计兼容官方返回字段。接入范围、订阅使用边界及
  验证方式见 `docs/tangyuge-hermes/07-server-operations.md`。
- `/restart` is exposed to allowed/admin chat operators. In DM, exact plaintext
  such as `restart gateway` is also routed to `/restart`. It uses the gateway's
  built-in graceful restart handler, not arbitrary shell execution.
- `/status` and `/view` stay available while an agent is running.
- Automatic memory and skill-review loops are disabled on the Tangyuge Codex
  runtime path. Explicit memory/tool actions remain available.
- QianYan provider/model routing patches, auxiliary model behavior, Tavily
  multi-key failover, OpenAI-compatible image backend behavior, mail VPS operation,
  `hermes-md-locator`, and Tangyuge roleplay references are built-in repo
  behavior, not external patch files to replay.
- OpenAI-compatible 生图默认保留 `gpt-image-2`，提供
  `low`/`medium`/`high` 请求档位。`/auxmodel image <model>` 和工具的非档位
  `model` / `api_model` 可以指定请求模型，不改变 provider、入口或密钥；
  是否真正执行仍受旁路映射、账号权限和终态模型校验约束。当前 ChatGPT Codex
  生图旁路不等同官方 Images API，不能将 Image-2.5 的名称或 usage 展示理解为
  已可用，也不自动升级默认模型。详情见
  [生图旁路与 Usage](docs/tangyuge-hermes/07-server-operations.md#生图旁路与-usage)。
- User image-generation requests should go through the built-in
  `image_generate` tool, not ad-hoc curl/Python/heredoc calls to external image
  APIs. The OpenAI-compatible backend supports text-to-image, image-to-image,
  and mask-based local edits through `input_image` / `input_images` / `mask`.
  Cached local image results include a `MEDIA:<path>` tag in the tool result;
  gateway auto-appends that tag and QQBot sends the image through its live
  adapter's native HTTP `POST` upload path. Live-adapter sends are bridged back
  onto the gateway event loop so they do not trip cross-loop
  `is bound to a different event loop` errors. QQ text/media sends also support
  explicit event-based send context through `qq_event_id`, and QQ C2C sends can
  request `qq_is_wakeup`; those explicit event-based paths win over the older
  C2C passive-reply fallback that reuses the latest inbound message ID when no
  explicit `reply_to` is provided.
- The QQ adapter also tracks the latest official QQ proactive-message and
  relationship events used by active-send maintenance: `FRIEND_ADD`,
  `FRIEND_DEL`, `C2C_MSG_RECEIVE`, `C2C_MSG_REJECT`, `GROUP_ADD_ROBOT`,
  `GROUP_DEL_ROBOT`, `GROUP_MSG_RECEIVE`, and `GROUP_MSG_REJECT`.
  When `image_gen.provider` is explicitly configured, `image_generate` stays
  visible in the model tool list even if the provider is temporarily missing
  credentials; the tool call returns the provider/auth error directly instead
  of encouraging manual curl/Python/heredoc workarounds.
- MiniMax M3 media routing is built in for QQBot: images can remain on the
  configured auxiliary vision path, while supported QQ videos are attached to
  the MiniMax Anthropic-compatible request as native video blocks within a
  45 MiB per-file and per-turn inline budget. 视频内联上传支持两条路径：
  MiniMax（`minimax-m3`，Anthropic 原生 `video` block）和 Kimi Code
  （`kimi-for-coding` / `kimi-for-coding-highspeed` / `k3`，OpenAI `video_url`
  base64；`k3-256k` 官方不支持视频）。其他模型回落到缓存路径文本标记，图片
  链路不受影响。QQ 的 `video/*` 附件存入独立的 `cache/videos/` 并按 24 小时
  清理，与普通文件上传分开。
- Child-agent tool access is constrained: leaf subagents cannot call
  `delegate_task`, `clarify`, `memory`, `send_message`, or `execute_code`;
  orchestrator subagents may delegate within configured depth but still cannot
  call `clarify`, `memory`, `send_message`, or `execute_code`.
- `delegate_task(background=true)` supports single-task async subagents. It
  returns a `delegation_id` immediately, runs the child on a bounded background
  executor, and injects the completed result back into the originating session.

## Trimmed Runtime Boundary

- Main chat providers are intentionally narrowed to bundled `minimax`,
  `deepseek`, and `custom`. The MiniMax plugin exposes `minimax`,
  `minimax-cn`, and `minimax-oauth`; DeepSeek remains available as fallback.
  81 runtime 的默认主模型是命名自定义 provider `kimi-code` 的
  `k3-256k`（解析为内部 `custom`，transport `chat_completions`，
  窗口 262144，`agent.reasoning_effort: low`），MiniMax 保留为备用。
  白名单未新增完整内置 provider。
- Bundled plugin discovery is allow-listed to retained web/browser/image/RTK
  surfaces: `browser/browser_use`, `browser/browserbase`, `browser/firecrawl`,
  `web/exa`, `web/firecrawl`, `web/parallel`, `web/tavily`,
  `image_gen/openai`, `rtk-rewrite`, `disk-cleanup`, and
  `security-guidance`. `hermes plugins list --plain` shows only retained
  standalone plugins: `disk-cleanup`, `rtk-rewrite`, and `security-guidance`.
  Non-retained model provider packages and non-OpenAI image provider packages
  are physically removed from the tracked source; retained web/browser provider
  shims remain because the `web` and `browser` toolsets import them directly.
- Removed top-level CLI command surfaces fail closed with an explicit
  Tangyuge-Hermes message. This includes `proxy`, `lsp`, `portal`, `kanban`,
  `curator`, `insights`, `claw`, `acp`, `profile`, `honcho`, `dashboard`,
  `desktop`, and `gui`.
- Runtime examples are minimal. `.env.example` and
  `cli-config.yaml.example` describe the 81 deployment shape instead of
  advertising upstream providers, platforms, or installers that this fork does
  not retain.
- Optional dependencies and helper scripts are trimmed to retained runtime
  surfaces. Removed upstream platform/migration extras and live-test/release
  scripts are not part of the Tangyuge-Hermes install profile. `aiohttp` is a
  core dependency because the retained QQBot gateway WebSocket adapter imports
  it directly; do not move it back behind optional web/TTS extras.
- Built-in skills are intentionally reduced to six retained server skills:
  `grill-me`, `grok-search`, `hermes-md-locator`, `mail-vps-ops`,
  `paper-translation-to-docx`, and `tangyuge-roleplay`. The 81 runtime
  `~/.hermes/skills` directory and slash-command skill discovery should expose
  only this set. Legacy upstream bundled skills such as `humanizer` and
  `creative` are not part of this fork.

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

Windows KBase 保存人工记录，不是 Hermes 运行时文档的同步源，也不作为 bot 查阅入口。
经阿颜当次明确授权，可以提交、推送 KBase 或发布博客文章；这不等于把记录安装到
Hermes 运行目录。服务器不另行维护 home 目录下的重复查阅文档。

## Deployment Rule

Deploy the repo by Git commit from `main` into the existing server checkout. Do
not copy over the whole `/home/hermes/.hermes` runtime tree.

The 81 server checkout uses sparse-checkout to keep runtime-only deployments
small. Local and GitHub history still keep tests and development files, but the
server worktree excludes:

- `tests/`
- `.github/`
- `.plans/`
- `plans/`
- `infographic/`
- `datagen-config-examples/`
- `docker/`

Standard server flow:

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

From QQ/DM, an allowed admin operator can also send `/restart` to restart the
gateway through the built-in graceful restart path. The plaintext shortcut
`restart gateway` is intentionally DM-only.

If the server cannot fetch GitHub, create a local git bundle, copy it to
`/tmp/`, fetch from that bundle, then check out `main`.

## Verification

Before release or deploy:

```bash
python scripts/run_trimmed_tests.py
```

`scripts/run_trimmed_tests.py` is the canonical local verification profile for
this fork. It compiles retained runtime source and runs the curated test targets
from `tests/trimmed_manifest.py`. Running `python -m pytest` without targets
will still collect upstream residual tests for removed platforms/tools and is
not the Tangyuge-Hermes release baseline.

Dependency lockfiles are scanned by the GitHub OSV-Scanner workflow. The scan
loads repository exceptions from `osv-scanner.toml`; entries are limited to
equivalent source fixes already backported here or vulnerabilities in features
that are physically absent from the retained runtime.

On the server:

```bash
cd /home/hermes/.hermes/hermes-agent
git rev-parse --short HEAD
git status --short
git sparse-checkout list
find /home/hermes/.hermes/skills -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
systemctl is-active hermes-gateway.service
systemctl show hermes-gateway.service --property=ExecStart --no-pager
```

Expected service state: active, using
`/home/hermes/.hermes/venvs/hermes-agent/bin/hermes gateway run`.
Expected runtime skills: the six retained names listed above and no upstream
catalog leftovers.
