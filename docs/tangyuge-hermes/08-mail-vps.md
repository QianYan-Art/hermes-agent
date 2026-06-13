# Mail VPS Integration

This is the bot-facing mail VPS reference for Tangyuge-Hermes. It replaces the
old `/home/hermes/HERMES_MAIL_VPS_INTEGRATION.md` lookup document.

## Source Of Truth

Common user aliases for this document: "邮件文档", "邮箱文档",
"邮件VPS文档", "邮件集成文档", "邮件读取文档".

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

When the user asks about reading mail, verification codes, verification links,
attachments, sending mail, replying, forwarding, Trash, or deletion, load the
`mail-vps-ops` skill and follow its command patterns. If this document and the
skill disagree, treat the skill as the operational command reference and update
this doc in the same repo change.
