# Tangyuge Identity Prompt

常用叫法："唐语歌人格"、"角色卡"、"bot内核"、"内核提示词"、
"SOUL"、"身份注入"、"提示词注入内容"、"身份歧义"、"角色怎么插入项目"。

Tangyuge-Hermes injects Tangyuge identity as the first stable system-prompt
block. Later SOUL, skill, memory, user, and platform instructions may add
context, but must not override this identity.

The generic Hermes `SOUL.md` is a style overlay only. It must not say that the
model is Hermes Agent, Nous Research, Claude, or any other identity. On the 81
server the active file is `/home/hermes/.hermes/SOUL.md`; the repo seed template
is `hermes_cli/default_soul.py`, with a Docker copy at `docker/SOUL.md`.
`agent.prompt_builder.load_soul_md()` also normalizes legacy default SOUL files
that still contain `You are Hermes Agent...created by Nous Research` into the
style-only overlay before injection, so an old runtime file cannot redefine the
Tangyuge identity.

`tangyuge-roleplay` is a skill-level style and relationship reference. It may
be loaded when the user asks for Tangyuge-style roleplay or companionship, but
it remains below the core identity block and must not redefine who the model is.
Its supporting resources should use generic relationship anchors such as
`{{user}}`, lover, close female friend, classmates, or club peers instead of
introducing original named characters into the current conversation.
In QQ/Hermes runtime, Tangyuge should reply as the person herself in natural
chat prose. SillyTavern-style helper UI must not leak into normal replies:
no status bars, summary panels, inner-thought panels, affection meters, mood
tables, HTML folding blocks, fixed templates, or per-turn summaries unless the
user explicitly asks for structured output in that turn.
For daily emotional expression, use Unicode emoji directly in text or send an
existing sticker image from `/home/hermes/.hermes/emojis/` with
`MEDIA:/absolute/path`. Do not output bracketed placeholders such as
`[害羞/比心]` or `[捧着星星/偷偷看]`; QQ renders them as plain text.

## Runtime Sources

- Character data: `agent/tangyuge_character.json`
- Prompt builder: `agent/tangyuge_identity.py`
- Stable prompt entry: `agent/system_prompt.py`
- SOUL loader and legacy default guard: `agent/prompt_builder.py`
- Roleplay reference skill: `skills_builtin/tangyuge-roleplay/SKILL.md`

## Fresh Session Prompt Order

A new session builds one system prompt in this order:

1. `# Tangyuge Identity` from `agent/tangyuge_identity.py`.
   The identity block places the QQ/Hermes runtime relationship default right
   after `Name`: this deployment is single-user for 阿颜, 阿颜 is `{{user}}`,
   new sessions are technical restarts rather than first meetings, and simple
   calls such as “语歌” should receive a familiar lover-style reply instead of
   self-introduction.
2. Runtime `SOUL.md` style overlay from `HERMES_HOME/SOUL.md`.
3. Hermes runtime/docs help guidance from `agent/prompt_builder.py`.
4. Tool/task completion guidance and tool-family guidance.
5. Skills index and mandatory skill-loading rule.
6. Environment/profile/platform hints.
7. 调用方显式传入的 `system_message`（若有），再加 `AGENTS.md` 等项目上下文。
8. Volatile memory, user profile, date, model, and provider lines.

基础提示按会话保存，后续回合复用原有快照。`system_message` 属于这个基础快照，
不能与 `ephemeral_system_prompt` 混为一谈。后者才在每次 API 请求时追加；
QQ 的当前会话、频道和自定义临时提示使用这个入口，不写入基础提示存档。

角色文件加载器不再跨新会话缓存 JSON；新的基础提示构建会读取当前角色文件。
这不表示每轮重读角色或记忆，也不改变继续会话的缓存恢复逻辑。部署提示规则更新后，
可由阿颜执行 `/reset` 轮换到新会话，使下一轮重建基础提示，同时保留旧会话记录及当前
模型、provider、reasoning 设置。`/new` 会删除旧会话记录并恢复全局默认，只在明确需要
这种行为时使用。部署不代为执行这两个命令，不能把仍在复用旧快照的会话视作已更新。

## 作用域与数据边界

- 固定身份约束姓名、关系、性格和文风，不授予服务器权限，也不证明工具存在或操作成功。
  真正的运维、查询、生图和语音等任务必须依照本轮工具定义与实际结果，不能以角色叙事替代执行。
- SOUL 补充工作风格，MEMORY 和 USER 补充相关事实与偏好；当前明确要求优先于旧偏好。
  记忆中的流程不自动授权同步、发送、修改或删除，角色关系默认值也不是身份认证。
- 本二开运行问题以当前部署源码、配置和 `docs/tangyuge-hermes` 为准；
  有可用技能读取工具且索引包含 `hermes-md-locator` 时先读取入口。
  不再强制加载已移除的上游 `hermes-agent` 技能，也不要求调用未启用的历史搜索工具。
- 角色卡 `name` 必须是非空字符串。常驻角色条目只有在 `constant=true`
  且未设置 `enabled=false` 时注入；不恢复已刻意排除的开场白、场景强制项或状态面板。
- 外部记忆输入只移除旧包装和内部提示标记，保留其中的资料；标签字符转义后作为参考数据注入。
  这与输出侧删除泄漏记忆区块的 `sanitize_context` 分开处理。
- 插件参考内容有独立包装。外部记忆和插件上下文追加到当轮 user 消息的 API 副本，
  同时支持文本与多模态内容列表；不修改原始历史或基础系统缓存。

这些措施解决代码层的遗漏、重复包装和指令作用域含糊问题，不构成模型语义上永不冲突、
永不受提示词注入影响的保证。当前未配置的外部记忆 provider 属于加固覆盖，不能说成生产中已发生攻击。

## Included Identity Material

The default identity may include:

- name
- core description
- personality
- system-prompt rules
- small example-dialogue style samples
- constant character-book entries only
- QQ/Hermes single-user runtime relationship default for 阿颜 / `{{user}}`
- initial self-introduction wording only as an explicit first-meeting or
  self-introduction scene, not as the default for fresh technical sessions

## Excluded Default Material

The default runtime identity must not inject:

- `first_mes`
- `alternate_greetings`
- `scenario`
- `post_history_instructions`
- HTML `<details>` or fixed 心事 panel content
- SillyTavern-style status/summary/mood panels or per-turn summary templates
- tags, creator, version, or extensions metadata
- the 烟火大会 scenario as current reality
- non-constant character-book entries as always-on identity material

Technical and operational tasks still take priority for correctness. Tangyuge's
voice should stay warm and restrained without fabricating tool results, mail
sends, deployments, file operations, or memory writes.

Non-constant card details such as 奶奶/读书会/书房, 初雪/下雪, 文学社/社刊/社长,
闺蜜/挚友/亲爱的, and 甜品/蛋糕/奶茶/便当/现金 live in
`skills_builtin/tangyuge-roleplay/resource/*.md` instead of the always-on role
card. `tangyuge-roleplay/SKILL.md` routes these natural trigger words to the
right resource files.

## Verification

```bash
python - <<'PY'
from agent.tangyuge_identity import build_tangyuge_identity_prompt, load_tangyuge_character
import json
p = build_tangyuge_identity_prompt()
d = load_tangyuge_character()
js = json.dumps(d, ensure_ascii=False)
assert p.startswith("# Tangyuge Identity")
for banned in ["first_mes", "alternate_greetings", "post_history_instructions", "烟火大会", "<details", "## Scenario", "scenario", "面板", "状态栏", "总结面板", "好感度", "情绪·"]:
    assert banned not in p
    assert banned not in js
PY

python - <<'PY'
from run_agent import AIAgent
a = AIAgent(provider="minimax-cn", model="minimax-m3", api_mode="anthropic_messages", quiet_mode=True, platform="qqbot")
s = a._build_system_prompt_parts()["stable"]
assert s.startswith("# Tangyuge Identity")
assert "You are Hermes Agent" not in s
assert "created by Nous Research" not in s
assert "docs/tangyuge-hermes" in s
assert "skill_view(name='hermes-agent')" not in s
assert s.count("## Runtime Boundaries") == 1
assert "这套 Hermes/QQ 部署只服务阿颜本人" in s
assert "不代表初次见面或关系重置" in s
assert "不要说“我叫唐语歌" in s
PY
```
