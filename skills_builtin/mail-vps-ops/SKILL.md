---
name: mail-vps-ops
description: 当用户要求读取邮件 VPS 上的邮箱列表、最新邮件、验证码、验证链接、附件，或执行发信、回复、转发、移到Trash、删除邮件时，必须使用本技能。支持通过 QQ 把附件发回给用户。
---

# 邮件 VPS 操作技能

## 目标

通过 Hermes 服务器上的受限 SSH key 连接邮件 VPS，完成邮件读取、验证码/验证链接提取、附件取回，以及受控的邮件发送/删除操作。

当前邮件 VPS 连接目标：

- `23.238.70.240:23333`
- 邮件服务域名保持为 `mail.qianyan.me`

## 固定命令

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py list-mailboxes
/home/hermes/.hermes/bin/mail_vps_fetch.py read-mail --email <完整邮箱地址>
/home/hermes/.hermes/bin/mail_vps_fetch.py list-attachments --email <完整邮箱地址>
/home/hermes/.hermes/bin/mail_vps_fetch.py fetch-attachment --email <完整邮箱地址>
```

写操作：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py send-mail ...
/home/hermes/.hermes/bin/mail_vps_fetch.py reply-mail ...
/home/hermes/.hermes/bin/mail_vps_fetch.py forward-mail ...
/home/hermes/.hermes/bin/mail_vps_fetch.py move-mail-to-trash ...
/home/hermes/.hermes/bin/mail_vps_fetch.py delete-mail ...
```

## 读操作范式

列出邮箱：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py list-mailboxes
/home/hermes/.hermes/bin/mail_vps_fetch.py list-mailboxes --domain mail.qianyan.me
```

读取最新邮件：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py read-mail --email user@mail.qianyan.me
/home/hermes/.hermes/bin/mail_vps_fetch.py read-mail --email user@mail.qianyan.me --require-code --want message_ref,codes,snippet,attachments
/home/hermes/.hermes/bin/mail_vps_fetch.py read-mail --email user@mail.qianyan.me --require-link --want message_ref,subject,verification_links,snippet
```

读取 Qwen 等链接型注册邮件时，优先使用 `--require-link`，并读取 `verification_links` 字段；不要把页脚年份等普通数字当验证码。
如果返回里存在 `verification_link_exports` / `preferred_media_tag`，说明系统已经把原始链接导出成 Hermes 本地 txt 文件；当链接较长、包含 token、或可能被模型自动脱敏时，优先把这个 txt 文件通过 QQ 发给用户。

列出附件：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py list-attachments --email user@mail.qianyan.me --message-ref cur/xxxx
```

取回附件：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py fetch-attachment --email user@mail.qianyan.me --message-ref cur/xxxx --attachment-index 1
```

## 通过 QQ 发附件

当用户明确要求“把附件发给我”时：

1. 先运行 `fetch-attachment`。
2. 查看返回 JSON 中的 `media_tag`。
3. 回复里单独输出这一行 `MEDIA:/绝对路径`，让网关原生发文件。
4. 如需要说明文字，把说明放在 `MEDIA:` 之前的普通文本里。

不要把本地缓存路径解释成长段文字，也不要遗漏 `MEDIA:` 前缀。

## 通过 QQ 发原始验证链接

当用户要“验证链接”“原始链接”“不要脱敏的链接”时：

1. 先运行：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py read-mail --email user@mail.qianyan.me --require-link --want message_ref,subject,verification_links,snippet
```

2. 如果返回里有 `verification_link_exports` 或 `preferred_media_tag`：
   直接输出 `preferred_media_tag` 对应的 `MEDIA:/绝对路径`，把原始链接 txt 发给用户。
3. 如果同时要在文字里展示链接：
   只能逐字原样输出，放进 fenced code block。
4. 不要把验证链接改写成 markdown 超链接，不要省略 query 参数，不要把中间字段写成 `***`、`...` 或“已脱敏”。

优先级：原始 txt 文件 > 纯文本复述。

## 写操作范式

发信：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py send-mail --from-email shi@mail.qianyan.me --to user@example.com --subject "主题" --body "正文"
```

回复：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py reply-mail --email shi@mail.qianyan.me --message-ref cur/xxxx --from-email shi@mail.qianyan.me --body "回复正文"
```

转发：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py forward-mail --email shi@mail.qianyan.me --message-ref cur/xxxx --from-email shi@mail.qianyan.me --to other@example.com --body "转发说明"
```

移到 Trash：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py move-mail-to-trash --email shi@mail.qianyan.me --message-ref cur/xxxx
```

永久删除：

```bash
/home/hermes/.hermes/bin/mail_vps_fetch.py delete-mail --email shi@mail.qianyan.me --message-ref cur/xxxx
```

## 使用规则

1. 用户没说邮箱地址时，先追问完整邮箱地址。
2. 读邮件默认只看最新 1 封。
3. 需要后续操作时，优先保留 `message_ref`。
4. 附件发送前先列附件，确认索引或名称。
5. `move-mail-to-trash` 和 `delete-mail` 属于破坏性操作，执行前必须在回复里明确说明即将删除哪封邮件。
6. `send-mail`、`reply-mail`、`forward-mail` 执行前，必须在回复里明确说明发件人、收件人、主题和正文摘要。

## 注意事项

- 只读操作与写操作走的是不同的受限 key。
- 这套链路不需要在 Hermes 服务器上搭代理。
- `fetch-attachment` 会把附件缓存到 Hermes 本地，发完后应尽量提醒后续清理。
- 不要输出私钥内容、邮箱密码或整封敏感正文。
