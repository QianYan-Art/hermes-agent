---
name: hermes-md-locator
description: 当用户用简单话要求找 Tangyuge-Hermes 文档时必须使用本技能，包括“全局状态”“当前状态”“维护手册”“重启网关命令”“自动清理session任务”“session清理timer”“部署文档”“81服务器”“项目总览”“二开方案”“精简方案”“角色卡/唐语歌人格/内核提示词”“tangyuge-roleplay”“角色扮演skill”“陪聊skill”“内置skills”“locator技能”“patch记录”“/new和/reset”“/view”“/context”“上下文窗口”“关闭自动记忆”“RTK”“MiniMax”“视频链路”“视频阈值”“图片识别”“媒体路由”“升级冻结”“邮件文档”“邮箱文档”“验证码/附件/发信”等。
---

# Tangyuge-Hermes 文档入口

## 目标

本技能是顶层文档入口，负责把用户的自然说法映射到仓库内的固定文档。服务器上的 bot 也应读取 repo `docs/tangyuge-hermes/`，不再依赖 home 目录文档副本。

路由优先级：

1. 先按本技能的快速路由表和组合路由定位。
2. 如果用户说法不在表内，按 repo 文档标题、常用叫法和正文关键词做内容定位。
3. 仍不确定时，先读 `00-overview.md` 和最可能的专题文档，再说明不确定点。

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

本地 KBase 只保留人工记录，不作为 bot 定位源；81 服务器不再维护 home 目录下的旧文档副本。

## 快速路由表

先按用户原话匹配下表；不要凭记忆猜路径。

| 用户常用说法 | 读取文档 |
| --- | --- |
| "总览", "项目总览", "整体情况", "二开项目", "tangyuge-hermes 是什么", "文档目录" | `docs/tangyuge-hermes/00-overview.md` |
| "部署", "部署文档", "81部署", "81服务器部署", "服务器怎么部署", "靠什么部署", "main分支部署", "服务命令", "旧版本还保留吗" | `docs/tangyuge-hermes/01-deployment-81.md` |
| "精简方案", "删了什么", "保留什么", "保留平台", "保留toolsets", "为什么docs还有这些", "项目裁剪" | `docs/tangyuge-hermes/02-trim-plan.md` |
| "唐语歌人格", "角色卡", "bot内核", "内核提示词", "SOUL", "身份注入", "角色怎么插入项目" | `docs/tangyuge-hermes/03-identity-prompt.md` |
| "tangyuge-roleplay", "角色扮演skill", "陪聊skill", "唐语歌skill", "角色卡和skill关系" | `docs/tangyuge-hermes/03-identity-prompt.md` and `docs/tangyuge-hermes/04-built-in-skills.md` |
| "内置skills", "skills列表", "有哪些skill", "locator技能", "mail-vps-ops", "技能怎么内置" | `docs/tangyuge-hermes/04-built-in-skills.md` |
| "patch记录", "二开patch", "/new和/reset", "/view", "/context", "上下文窗口", "关闭自动记忆", "自动总结skills", "RTK", "provider", "模型路由", "Tavily", "HYBGZS", "新旧行为差异" | `docs/tangyuge-hermes/05-patches-and-rtk.md` |
| "MiniMax", "minimax-m3", "视频链路", "视频阈值", "45 MiB", "图片识别", "媒体路由", "native video", "视频直传", "视频预算" | `docs/tangyuge-hermes/05-patches-and-rtk.md` and `docs/tangyuge-hermes/07-server-operations.md` |
| "升级冻结", "上游升级", "能不能合并上游", "release规则", "tag规则", "版本冻结" | `docs/tangyuge-hermes/06-upgrade-freeze.md` |
| "维护手册", "全局状态", "当前状态", "服务器状态", "服务器全局状态", "运行状态", "重启网关命令", "缓存目录", "session清理", "自动清理session任务", "session cleanup", "retention cleanup", "timer", "memory/user文档", "权限", "blogsync", "检查网关" | `docs/tangyuge-hermes/07-server-operations.md` |
| "邮件文档", "邮箱文档", "邮件VPS文档", "邮件集成文档", "读邮件", "验证码", "验证链接", "附件", "发信", "回复邮件", "转发邮件", "删除邮件" | `docs/tangyuge-hermes/08-mail-vps.md` |

## 组合路由

- "全局状态"、"服务器状态"、"当前状态"：先读 `07-server-operations.md`；涉及部署版本或服务来源时再读 `01-deployment-81.md`。
- "维护手册里查重启网关命令"、"重启网关"：读 `07-server-operations.md` 的 Chat-side restart / Chinese operator phrasing。
- "自动清理session任务"、"session清理timer"、"retention cleanup"：读 `07-server-operations.md` 的 Session Cleanup Timer。
- "服务器怎么部署、旧版本还在不在、靠什么启动"：读 `01-deployment-81.md` 和 `07-server-operations.md`。
- "我的patch是否内置、/new和/reset差异、/view、/context、上下文窗口、自动记忆/skills总结关闭"：读 `05-patches-and-rtk.md`；涉及技能清单再读 `04-built-in-skills.md`。
- "MiniMax、视频链路、视频阈值、图片识别、媒体路由"：读 `05-patches-and-rtk.md` 和 `07-server-operations.md`；只问当前服务器状态时先读 `07-server-operations.md`。
- "bot怎么成为唐语歌、角色卡怎么进内核"：读 `03-identity-prompt.md`；涉及运行时文件边界再读 `00-overview.md`。
- "tangyuge-roleplay、角色扮演skill、陪聊skill、角色卡和skill关系"：读 `03-identity-prompt.md` 和 `04-built-in-skills.md`。
- "邮件/邮箱/验证码/附件"：读 `08-mail-vps.md`，然后加载 `mail-vps-ops` 执行实际邮箱操作。
- "文档在哪、KBase和服务器文档关系"：读 `00-overview.md` 和 `07-server-operations.md`。

## 触发语义

用户说以下内容时，优先使用本技能：

- “总览”“项目总览”“整体情况”“二开项目”“文档目录”
- “部署文档”“81部署”“81服务器部署”“服务器怎么部署”“靠什么部署”
- “旧版本还保留吗”“main分支部署”“服务命令”
- “精简方案”“删了什么”“保留什么”“项目裁剪”
- “角色卡”“唐语歌人格”“bot内核”“内核提示词”“SOUL”“身份注入”
- “tangyuge-roleplay”“角色扮演skill”“陪聊skill”“唐语歌skill”“角色卡和skill关系”
- “内置skills”“有哪些skill”“locator技能”“技能怎么内置”
- “patch记录”“二开patch”“/new和/reset”“/view”“/context”“上下文窗口”“关闭自动记忆”“自动总结skills”“RTK”
- “MiniMax”“minimax-m3”“视频链路”“视频阈值”“45 MiB”“图片识别”“媒体路由”“native video”“视频直传”“视频预算”
- “语歌，全局状态”“语歌，看维护手册”“语歌，看邮箱文档”“语歌，查邮件文档”
- “语歌，看唐语歌内核方案”“语歌，看精简方案”“语歌，看 RTK 和 patch 文档”
- “语歌，看部署方案”“语歌，看二开总方案”“语歌，看内置 skills 方案”
- “维护手册”“看维护手册”“查维护手册”“打开维护手册”
- “去维护手册里查重启网关命令”“维护手册里查 /restart”“重启网关命令”
- “自动清理session任务”“session清理任务”“session清理timer”“session cleanup”“retention cleanup”
- “唐语歌维护手册”“唐语歌人格维护手册”“Hermes维护手册”
- “全局状态”“当前状态”“服务器状态”“服务器全局状态”
- “全局状态文档”“当前服务器全局状态文档”
- “邮件文档”“邮件VPS文档”“邮件集成文档”“邮件读取文档”“邮件技能文档”
- “邮箱文档”“看邮箱文档”“查邮箱文档”
- “验证码”“验证链接”“邮件附件”“发邮件”“回复邮件”“转发邮件”“删邮件”
- “按维护手册处理”“按全局状态文档核对”
- “之前做了什么 patch”“当前有哪些补丁”“更新时要保留什么”
- “tangyuge-hermes 二开”“二开方案”“部署方案”“当前 mission 方案”

## 使用规则

1. 用户问“维护手册、如何维护、如何重启、如何删除 skill、如何改配置、日常操作步骤”时，读取 `docs/tangyuge-hermes/07-server-operations.md`。
2. 用户问“全局状态、当前状态、服务器状态、网关状态”时，读取 `docs/tangyuge-hermes/07-server-operations.md` 和 `docs/tangyuge-hermes/01-deployment-81.md`。
3. 用户问“邮件 VPS、读邮件、附件、发信、回复、转发、Trash、删除、邮件 skill”时，读取 `docs/tangyuge-hermes/08-mail-vps.md`。
4. 用户问“更新、diff、patch、当前真实配置、启用工具集、provider、模型、memory、skills”时，读取 `docs/tangyuge-hermes/05-patches-and-rtk.md`、`docs/tangyuge-hermes/07-server-operations.md` 和相关专题文档。
5. 用户问 tangyuge-hermes 二开、部署方案、当前实现边界时，优先读取本技能列出的 repo 文档。
6. 用户问表内没有的新主题时，按 repo docs 的标题、常用叫法和正文关键词定位；不要因为路由表没有列出就回答“没有文档”。
7. 不要凭记忆猜路径；先使用上面的 repo 固定路径。
8. 文档和当前仓库/服务器状态冲突时，必须说明“文档可能过期”，再建议现场核验命令。

## 注意事项

- 不要把 API key、bot token、私钥内容输出给用户。
- 本技能只定位和读取文档；真正修改服务器、重启网关、清理文件前，仍要按 repo 文档和当前现场状态逐项核对。
- 每次 repo `docs/tangyuge-hermes/` 或 README 增删主题、改常用叫法、改当前运行状态时，都要检查并同步更新本技能的 description、快速路由表、组合路由和触发语义。
