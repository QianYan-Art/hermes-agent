# Built-In Skills

常用叫法："内置skills"、"skills列表"、"有哪些skill"、"locator技能"、
"mail-vps-ops"、"技能怎么内置"。

Tangyuge-Hermes retains exactly six built-in skills for the 81 server workflow:

- `grill-me`
- `grok-search`
- `hermes-md-locator`
- `mail-vps-ops`
- `paper-translation-to-docx`
- `tangyuge-roleplay`

These live under `skills_builtin/` and are loaded before local/external skill
directories so clean installs can discover them without copying server-local
skill folders into the repo.

The 81 server runtime mirrors this exact set under
`/home/hermes/.hermes/skills`. The runtime should not contain the upstream
bundled skill catalog. In particular, broad upstream skills such as
`humanizer` and `creative` are removed and should not reappear in
`skills_list`, slash-command skill discovery, or filesystem checks.

## Skill Boundaries

- `tangyuge-roleplay` 补充语感、情境与角色细节；核心身份来自
  `agent/tangyuge_identity.py`，不靠技能开关成立。身份块引导模型在工具可用、
  首次有实质性人格交流时主动调用 `skill_view`，入口再引导读取 `soul.md`
  及当前话题相关资源，无需用户提名，也不宣告加载。已有内容复用，不每轮重读；
  简短确认或纯技术操作不增加检索。工具不可用、技能被禁用或失败时不假装已读。
  这是提示引导，不是确定性自动注入，也不改写已存会话基础提示。
  新增 `resource/appearance_and_preferences.md` 路由外貌、立绘、发型、服装、
  甜品、奶茶、便当、现金、荷包与复古审美；其他资源承载读书、初雪、文学社、
  亲爱的等语感或背景话题。资源位于核心身份之下，不重复注入整张卡，不引入
  原作具名角色、年龄、学籍、固定职业或虚构共同记忆。
- `hermes-md-locator` is the dynamic documentation entrypoint. Keep its
  description, route table, combination routes, and trigger phrases aligned with
  current `docs/tangyuge-hermes/` and README content whenever bot-facing docs
  change.
- `grok-search` documents environment-variable based configuration only. Real
  secrets must remain in runtime environment or server-local config.
- `mail-vps-ops` 查询全部邮箱时默认覆盖所有域名，不添加 `--domain` 或
  数量限制，也不要求用户提供邮箱地址；只有用户明确指定域名时才过滤。
  邮件服务主机名不是邮箱域名白名单，具体规则见 `08-mail-vps.md`。
- Sub-agents default to no memory/skill mutation capability.

## Runtime Guard

The 81 runtime keeps `/home/hermes/.hermes/.no-bundled-skills` so upstream
bootstrap code does not repopulate removed bundled skills. If the runtime skill
list ever grows beyond the six retained names, treat it as drift and resync
from `skills_builtin/` after preserving any server-local secret files such as a
runtime `.env`.

## Verification

```bash
python -m hermes_cli.main skills list --enabled-only
find /home/hermes/.hermes/skills -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
```

The enabled list should show the six retained skills and no broad upstream skill
catalog. Slash-command skill discovery should resolve to the same six names.
