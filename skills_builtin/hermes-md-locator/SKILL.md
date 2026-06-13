---
name: hermes-md-locator
description: 当用户说“维护手册”“看维护手册”“查维护手册”“唐语歌维护手册”“Hermes维护手册”“全局状态”“当前状态”“服务器全局状态”“全局状态文档”“邮件VPS文档”“邮件集成文档”“邮箱文档”“看邮箱文档”“tangyuge-hermes 文档”等，需要读取或定位 Tangyuge-Hermes repo 文档、部署状态、维护说明、邮件 VPS 集成、更新补丁记录、配置路径时，必须使用本技能。
---

# Tangyuge-Hermes 文档入口

## 目标

本技能是顶层文档入口，负责把用户的自然说法映射到仓库内的固定文档。服务器上的 bot 也应读取 repo `docs/tangyuge-hermes/`，不再依赖 `/home/hermes/*.md` 维护副本。

## 固定文档路径

Tangyuge-Hermes 的 bot 可读主文档统一放在仓库内：

- 项目总览：`docs/tangyuge-hermes/00-overview.md`
- 81 部署：`docs/tangyuge-hermes/01-deployment-81.md`
- 项目精简：`docs/tangyuge-hermes/02-trim-plan.md`
- 唐语歌内核提示词：`docs/tangyuge-hermes/03-identity-prompt.md`
- 内置 skills：`docs/tangyuge-hermes/04-built-in-skills.md`
- Patch 与 RTK：`docs/tangyuge-hermes/05-patches-and-rtk.md`
- 升级冻结：`docs/tangyuge-hermes/06-upgrade-freeze.md`
- 服务器状态与维护：`docs/tangyuge-hermes/07-server-operations.md`
- 邮件 VPS 集成：`docs/tangyuge-hermes/08-mail-vps.md`

本地 KBase 只保留人工记录，不作为 bot 定位源；81 服务器不再维护 `/home/hermes/HERMES_*.md` 或 `/home/hermes/TANGYUGE_HERMES_*.md` 文档副本。

## 触发语义

用户说以下内容时，优先使用本技能：

- “语歌，全局状态”“语歌，看维护手册”“语歌，看邮箱文档”“语歌，查邮件文档”
- “语歌，看唐语歌内核方案”“语歌，看精简方案”“语歌，看 RTK 和 patch 文档”
- “语歌，看部署方案”“语歌，看二开总方案”“语歌，看内置 skills 方案”
- “维护手册”“看维护手册”“查维护手册”“打开维护手册”
- “唐语歌维护手册”“唐语歌人格维护手册”“Hermes维护手册”
- “全局状态”“当前状态”“服务器状态”“服务器全局状态”
- “全局状态文档”“当前服务器全局状态文档”
- “邮件VPS文档”“邮件集成文档”“邮件读取文档”“邮件技能文档”
- “邮箱文档”“看邮箱文档”“查邮箱文档”
- “按维护手册处理”“按全局状态文档核对”
- “之前做了什么 patch”“当前有哪些补丁”“更新时要保留什么”
- “tangyuge-hermes 二开”“二开方案”“部署方案”“当前 mission 方案”

## 使用规则

1. 用户问“维护手册、如何维护、如何重启、如何删除 skill、如何改配置、日常操作步骤”时，读取 `docs/tangyuge-hermes/07-server-operations.md`。
2. 用户问“全局状态、当前状态、服务器状态、网关状态”时，读取 `docs/tangyuge-hermes/07-server-operations.md` 和 `docs/tangyuge-hermes/01-deployment-81.md`。
3. 用户问“邮件 VPS、读邮件、附件、发信、回复、转发、Trash、删除、邮件 skill”时，读取 `docs/tangyuge-hermes/08-mail-vps.md`。
4. 用户问“更新、diff、patch、当前真实配置、启用工具集、provider、模型、memory、skills”时，读取 `docs/tangyuge-hermes/05-patches-and-rtk.md`、`docs/tangyuge-hermes/07-server-operations.md` 和相关专题文档。
5. 用户问 tangyuge-hermes 二开、部署方案、当前实现边界时，优先读取本技能列出的 repo 文档。
6. 不要凭记忆猜路径；先使用上面的 repo 固定路径。
7. 文档和当前仓库/服务器状态冲突时，必须说明“文档可能过期”，再建议现场核验命令。

## 注意事项

- 不要把 API key、bot token、私钥内容输出给用户。
- 本技能只定位和读取文档；真正修改服务器、重启网关、清理文件前，仍要按 repo 文档和当前现场状态逐项核对。
