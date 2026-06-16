# Tangyuge-Hermes Trim Plan

常用叫法："精简方案"、"删了什么"、"保留什么"、"保留平台"、
"保留toolsets"、"项目裁剪"、"服务器瘦身"、"sparse checkout"、
"README留几个"。

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

Do not physically remove plugin packages just because they are disabled on the
81 server. Some retained toolsets still import provider compatibility shims, for
example:

- `tools/web_tools.py` re-exports plugin-backed web providers.
- `tools/browser_tool.py` re-exports plugin-backed browser providers.
- image generation and model provider menus discover bundled plugin metadata.

Safe plugin trimming means first proving no retained toolset/import path depends
on that plugin. Until then, prefer runtime allow-listing over deleting files.

## Verification

```bash
git ls-files gateway/platforms plugins tools hermes_cli
git ls-files README.zh-CN.md
python -m hermes_cli.main --help
python -m hermes_cli.main tools list
```

Searches for removed platform/tool paths should return no tracked files, and
removed top-level commands should be rejected by argparse. `git ls-files
README.zh-CN.md` should print nothing.

Retained-scope test runs should target QQBot/API-server/CLI/cron and retained
toolsets only. Upstream tests for removed surfaces such as Signal platform
delivery or FAL video-generation plugins are not part of this fork's passing
baseline unless those surfaces are intentionally restored.
