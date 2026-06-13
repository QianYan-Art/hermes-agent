# Tangyuge-Hermes Trim Plan

Common user aliases for this document: "精简方案", "删了什么",
"保留什么", "保留平台", "保留toolsets", "项目裁剪".

Tangyuge-Hermes keeps only the 81 server QQBot/API-server operating scope and
removes non-retained runtime surfaces physically where practical.

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

## Verification

```bash
git ls-files gateway/platforms plugins tools hermes_cli
python -m hermes_cli.main --help
python -m hermes_cli.main tools list
```

Searches for removed platform/tool paths should return no tracked files, and
removed top-level commands should be rejected by argparse.
