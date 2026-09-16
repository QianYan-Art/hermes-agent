# Tangyuge-Hermes Overview

常用叫法："总览"、"项目总览"、"整体情况"、"二开项目"、
"tangyuge-hermes 是什么"、"文档目录"。

`tangyuge-hermes` is the 81 server QQBot-focused fork of Hermes Agent. The project baseline is frozen at Hermes Agent v0.16.0 (2026-06-05) and the 2026-06-12 81-server snapshot; this fork does not track upstream feature churn after that point.

The Python package name and CLI command remain `hermes` for compatibility with existing service files, scripts, imports, and local operator habits. Public-facing project documentation and release notes use the `tangyuge-hermes` name.

## Runtime Scope

This fork keeps the 81 server's daily QQBot workflow as the primary supported runtime:

- QQBot gateway operation.
- QianYan server patches already present in the snapshot.
- Tangyuge identity as the highest-priority model identity.
- Runtime `SOUL.md` as style overlay only; legacy default SOUL identity text is
  normalized away by the loader and should not exist in the active 81 file.
- The retained operational skills and RTK plugin path required by the server.

Non-server surfaces such as desktop apps, website/web UI, bootstrap installers, dashboard GUI, and TUI shells are outside the target runtime unless a later mission issue explicitly keeps a compatibility shim.

## Runtime Data Boundary

Server runtime data must stay outside the repository and must not be overwritten by deployment:

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

部署使用 `main`，核对工作区后执行 `git merge --ff-only`，不强制 reset 或覆盖运行配置。
外置虚拟环境使用 `/home/hermes/.hermes/venvs/hermes-agent`，避免依赖与源码、运行数据混用。

On the current 81 host, active generated-image and TTS files still land in the
top-level `image_cache/` and `audio_cache/` directories because those legacy
paths already exist. QQ 普通文件进入 `cache/documents/`，入站视频进入
`cache/videos/`，入站语音进入 `audio_cache/`。

## Documentation Layout

The bot-facing documentation source is this repository directory:

- `docs/tangyuge-hermes/00-overview.md`
- `docs/tangyuge-hermes/01-deployment-81.md`
- `docs/tangyuge-hermes/02-trim-plan.md`
- `docs/tangyuge-hermes/03-identity-prompt.md`
- `docs/tangyuge-hermes/04-built-in-skills.md`
- `docs/tangyuge-hermes/05-patches-and-rtk.md`
- `docs/tangyuge-hermes/06-upgrade-freeze.md`
- `docs/tangyuge-hermes/07-server-operations.md`
- `docs/tangyuge-hermes/08-mail-vps.md`

`hermes-md-locator` 仅定位这些仓库开发文档。KBase 保存人工记录，不是 Hermes
运行时文档的同步源；经阿颜当次授权可以发布为博客文章。服务器不另行维护 home
目录下的重复查阅文档，也不把博客文章目录作为 Hermes 文档入口。

## Documentation And Memory Rules

When project behavior changes, keep these sources aligned:

- Update repo docs under `docs/tangyuge-hermes/` first. These are the bot-facing
  source of truth and must be reachable through `hermes-md-locator`.
- When docs or README add/remove topics, aliases, or current-state facts, update
  `skills_builtin/hermes-md-locator/SKILL.md` in the same change so the bot can
  locate the new content from natural user phrasing.
- KBase 仅在阿颜明确授权后更新；默认只保留本地 operator notes，不提交、不推送、
  不执行博客同步。相应发布动作须阿颜当次另行明确授权；公开文章同步不等于将
  KBase 安装到 Hermes 运行目录，不改变 bot 只定位仓库开发文档的规则。
- NowledgeMem/nmem 与 Serena 是维护侧记忆，仅在阿颜明确授权后写入、合并、
  替换或删除。优先更新既有 Tangyuge-Hermes 主条目，不新建平行状态条目；
  只记录长期稳定规则、当前主状态和关键部署事实，不记录流水账或密钥内容。
- `.doc-maintenance/` 仅存放本地临时审阅材料，必须被 Git 忽略，完成后清理；
  不得在 KBase 内生成此目录。
- When prompt, SOUL, identity, or roleplay behavior changes, verify both the
  always-on role card and `tangyuge-roleplay` skill boundary: the role card
  defines identity; the skill only adds style, relationship, and topic
  resources.
- 部署核验后清理临时 bundle、部署包和确认无用的旧文档/备份；删除前按
  `07-server-operations.md` 的 Cleanup Rule 核对引用、运行依赖与恢复价值，
  不把“备份较旧”或“没有运行引用”直接等同于可删除。

## Baseline Verification

Before release or deployment, verify the current commit and test evidence:

```bash
git rev-parse --short HEAD
python scripts/run_trimmed_tests.py
```

The `main` branch is the validated deployment line for the 81 server. The
trimmed verification profile lives in `tests/trimmed_manifest.py`; unscoped
`python -m pytest` is not the release baseline because it still discovers
upstream residual tests for removed platforms and tools.
