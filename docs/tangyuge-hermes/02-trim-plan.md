# Tangyuge-Hermes Trim Plan

常用叫法："精简方案"、"删了什么"、"保留什么"、"保留平台"、
"保留toolsets"、"项目裁剪"、"服务器瘦身"、"sparse checkout"、
"README留几个"、"CLI裁剪"、"removed commands"、"provider白名单"、
"插件白名单"、"依赖精简"、"scripts删除"。

Tangyuge-Hermes keeps only the 81 server QQBot/API-server operating scope and
removes non-retained runtime surfaces physically where practical.

`README.md` is the single repository entrypoint. Do not keep a parallel
`README.zh-CN.md`; duplicate README files drift and make upstream marketing text
easy to reintroduce by mistake.

## Retained Toolsets

Runtime toolsets are limited to:

- `web`
- `browser`
- `terminal`
- `file`
- `vision`
- `image_gen`
- `tts`
- `skills`
- `todo`
- `memory`
- `clarify`
- `delegation`
- `cronjob`
- `messaging`

`hermes tools list` should show only this retained set.

## Retained Runtime Skills

The repo and the 81 runtime retain exactly six project skills:

- `grill-me`
- `grok-search`
- `hermes-md-locator`
- `mail-vps-ops`
- `paper-translation-to-docx`
- `tangyuge-roleplay`

The server runtime directory `/home/hermes/.hermes/skills` is a deployment
mirror of this retained set, not a place for the upstream bundled skill catalog.
Slash-command skill discovery should expose the same six names. Upstream
general-purpose skills such as `humanizer` and `creative` are intentionally
removed from the server checkout and runtime home.

The 81 runtime keeps `/home/hermes/.hermes/.no-bundled-skills` as a guard file
to prevent upstream bundled skill bootstrap code from repopulating the broad
catalog after restarts or reinstalls.

## Retained Platforms

Retained platform/runtime entries:

- `qqbot`
- `api_server`
- `cli`
- `cron`

Gateway platform source is limited to API server, QQBot, and shared base/helper
files. Non-retained adapters such as Telegram, Discord, Slack, WhatsApp, Feishu,
WeCom, Matrix, Mattermost, webhook, and Yuanbao are outside this fork.

## Removed Surfaces

The fork removes web UI, website, desktop app, TUI shell, bootstrap installers,
non-retained platform plugins, non-retained tool plugins, and non-retained CLI
command surfaces such as `computer-use`, `whatsapp`, `slack`, and `webhook`.

Removed top-level CLI command surfaces fail closed instead of silently
dispatching to old upstream behavior:

- `proxy`
- `lsp`
- `portal`
- `kanban`
- `curator`
- `insights`
- `claw`
- `acp`
- `profile`
- `honcho`
- `dashboard`
- `desktop`
- `gui`

`memory` remains as a narrow local command group with `status`, `off`, and
`reset`; external setup/bootstrap memory commands are outside this fork.

Non-retained helper scripts are also removed from the tracked source when they
belong only to upstream live tests, release automation, Docker migrations,
Discord/WhatsApp adapters, Modal/Open WebUI helpers, Android installers, or
other non-retained deployment paths.

## Server Slimming

Local and GitHub `main` keep tests and development artifacts so the fork remains
reviewable and testable. The 81 server checkout is runtime-only and uses
sparse-checkout to exclude:

- `tests/`
- `.github/`
- `.plans/`
- `plans/`
- `infographic/`
- `datagen-config-examples/`
- `docker/`

This keeps the running checkout smaller without weakening the local/GitHub test
baseline.

## Plugin Boundary

Bundled plugins are not all runtime-enabled. The 81 runtime currently enables
only `rtk-rewrite` through `plugins.enabled`; other retained capabilities are
loaded by configured providers/toolsets or explicit user configuration.

Bundled plugin discovery is allow-listed to retained capabilities:

- `browser/browser_use`
- `browser/browserbase`
- `browser/firecrawl`
- `web/exa`
- `web/firecrawl`
- `web/parallel`
- `web/tavily`
- `image_gen/openai`
- `rtk-rewrite`
- `disk-cleanup`
- `security-guidance`

`hermes plugins list --plain` lists only retained standalone plugin manifests:

- `disk-cleanup`
- `rtk-rewrite`
- `security-guidance`

Do not physically remove retained provider shim packages solely because they
are not standalone plugins. Some retained toolsets still import compatibility
shims directly, for example:

- `tools/web_tools.py` re-exports plugin-backed web providers.
- `tools/browser_tool.py` re-exports plugin-backed browser providers.
- image generation and model provider menus discover bundled plugin metadata.

Safe plugin trimming means first proving no retained toolset/import path depends
on that plugin. The current tracked source physically removes non-retained model
provider packages and non-OpenAI image provider packages, while keeping retained
web/browser shims and the `image_gen/openai`, `rtk-rewrite`, `disk-cleanup`, and
`security-guidance` packages.

## Provider Boundary

Bundled model provider discovery is narrowed to:

- `custom`
- `deepseek`
- `minimax`

The visible provider registry should contain only `custom`, `deepseek`,
`minimax`, `minimax-cn`, and `minimax-oauth`. MiniMax is the default 81 runtime
provider; DeepSeek is the retained backup provider.

## Dependency Boundary

`pyproject.toml` optional dependencies are limited to retained runtime needs:
web search backends, `edge-tts`, dev/test, cron compatibility, CLI, PTY,
vision, MCP, and `[all]` as the small Tangyuge server install profile. Removed
upstream extras such as Slack, Matrix, WeCom, ACP, Modal, Daytona, Honcho,
HomeAssistant, SMS, Google/YouTube, premium TTS, upstream voice/STT extras
(not the retained QQBot STT path), Bedrock, Azure, Termux, DingTalk, Feishu,
FAL, and non-retained messaging stacks are outside the current install profile.

`aiohttp` is a core dependency, not an optional web/TTS dependency, because the
retained QQBot gateway WebSocket adapter imports `aiohttp` directly for
`ClientSession`, WebSocket receive types, and proxy-aware connection handling.
Keep the direct pin aligned with `uv.lock` and current GitHub advisory fixed
ranges so fresh 81-style installs do not rely on leftover server packages.

## Verification

```bash
git ls-files gateway/platforms plugins tools hermes_cli
git ls-files README.zh-CN.md
python -m hermes_cli.main --help
python -m hermes_cli.main tools list
python -m hermes_cli.main plugins list --plain
python -m hermes_cli.main proxy
```

Searches for removed platform/tool paths should return no tracked files, and
removed top-level commands should be rejected by argparse. `git ls-files
README.zh-CN.md` should print nothing.

Tracked plugin package checks should show only the retained model and image
provider directories:

```bash
git ls-files 'plugins/model-providers/*/plugin.yaml' | cut -d/ -f3 | sort -u
git ls-files 'plugins/image_gen/*/plugin.yaml' | cut -d/ -f3 | sort -u
```

The expected model providers are `custom`, `deepseek`, and `minimax`; the
expected image provider is `openai`.

Server runtime skill checks should show only the retained six skills:

```bash
find /home/hermes/.hermes/skills -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes \
  /home/hermes/.hermes/venvs/hermes-agent/bin/python -m hermes_cli.main skills list --enabled-only
find /home/hermes/.hermes -path '*/humanizer' -o -path '*/creative'
```

The first two commands should list only the six retained names. The final search
should print nothing.

Retained-scope test runs should target QQBot/API-server/CLI/cron and retained
toolsets only. Upstream tests for removed surfaces such as Signal platform
delivery or FAL video-generation plugins are not part of this fork's passing
baseline unless those surfaces are intentionally restored.

The current trim boundary and focused runtime regressions are covered by the
canonical trimmed profile:

```bash
python scripts/run_trimmed_tests.py
```

The profile source is `tests/trimmed_manifest.py`. It includes
`tests/hermes_cli/test_tangyuge_trim_scope.py` plus focused QQBot, approval,
image generation, MiniMax/DeepSeek provider, async delegation, RTK, identity,
and retained toolset checks. Do not treat unscoped `python -m pytest` as the
trimmed release baseline while upstream residual tests remain in the tree.
