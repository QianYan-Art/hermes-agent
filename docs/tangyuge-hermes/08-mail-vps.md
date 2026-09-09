# Mail VPS Integration

This is the bot-facing mail VPS reference for Tangyuge-Hermes. It replaces the
old home-directory mail lookup document.

## Source Of Truth

常用叫法："邮件文档"、"邮箱文档"、"邮件VPS文档"、"邮件集成文档"、
"邮件读取文档"、"邮箱列表"、"有哪些邮箱"、"多域名邮箱"、
"新域名邮箱漏列"、"sru.edu.kg"。

- Skill: `skills_builtin/mail-vps-ops/SKILL.md`
- Runtime helper: `/home/hermes/.hermes/bin/mail_vps_fetch.py`
- Bot lookup doc: `docs/tangyuge-hermes/08-mail-vps.md`

Secrets and mailbox credentials stay in server-local runtime configuration.
Do not copy secrets into repo docs, KBase records, chat replies, or commits.

## Supported Operations

Read/list operations:

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py list-mailboxes
/home/hermes/.hermes/bin/mail_vps_fetch.py read-mail --email <完整邮箱地址>
/home/hermes/.hermes/bin/mail_vps_fetch.py list-attachments --email <完整邮箱地址>
/home/hermes/.hermes/bin/mail_vps_fetch.py fetch-attachment --email <完整邮箱地址>
```

Write/delete operations:

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py send-mail ...
/home/hermes/.hermes/bin/mail_vps_fetch.py reply-mail ...
/home/hermes/.hermes/bin/mail_vps_fetch.py forward-mail ...
/home/hermes/.hermes/bin/mail_vps_fetch.py move-mail-to-trash ...
/home/hermes/.hermes/bin/mail_vps_fetch.py delete-mail ...
```

## 邮箱列表与域名范围

用户要求“列出全部邮箱”“邮件 VPS 有哪些邮箱”时，执行不带 `--domain` 和
`--limit` 的 `list-mailboxes`，不要求用户先提供邮箱地址。只有用户明确限定
域名时才添加过滤，例如：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py list-mailboxes --domain sru.edu.kg
```

`mail.qianyan.me` 是邮件服务主机名，也是其中一个邮箱域名，但不是邮箱域名
白名单。新增域名不能被历史示例或旧查询范围排除；实际域名及邮箱以当次返回
的 `mailboxes` 为准，可按域名分组完整展示。`matched` 是匹配总数，若大于
返回列表长度，不能称为完整清单，应去掉 `--limit` 重新查询。

81 helper 将显式 `--domain` 原样传给邮件 VPS；两端均不设置默认域名过滤。
邮件 VPS 的 `/usr/local/bin/hermes-mail-api.py` 枚举
`/var/mail/vmail/<domain>/<user>` 下已存在的邮箱目录，不是 DNS 或域名管理
接口，也不代表尚未创建邮箱目录的配置项或别名清单。

2026-09-09 排查确认：QQ 工具调用自行添加了 `--domain mail.qianyan.me`，
因而漏掉 `sru.edu.kg`。同一条受限 SSH 链路的不带过滤查询和指定新域查询
均能返回新域邮箱；修正范围是技能选参规则和文档，不需要改邮件脚本、
邮箱账号、凭据或服务配置。后续新增域名仍使用同一无过滤查询，不固化邮箱数量。

## Operating Rules

- For verification codes, read the newest relevant message and extract the code
  or verification link only.
- For link-based registration mail, preserve the original URL exactly. Do not
  summarize or rewrite query parameters.
- For attachments, list attachments first, then fetch the requested attachment.
- For destructive mail actions such as permanent delete, confirm target mailbox
  and message reference before acting.
- Do not expose credentials, tokens, cookies, or raw auth headers.

## Skill Routing

When the user asks about mailbox lists, reading mail, verification codes, verification links,
attachments, sending mail, replying, forwarding, Trash, or deletion, load the
`mail-vps-ops` skill and follow its command patterns. If this document and the
skill disagree, treat the skill as the operational command reference and update
this doc in the same repo change.
