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
2. Runtime `SOUL.md` style overlay from `HERMES_HOME/SOUL.md`.
3. Hermes runtime/docs help guidance from `agent/prompt_builder.py`.
4. Tool/task completion guidance and tool-family guidance.
5. Skills index and mandatory skill-loading rule.
6. Environment/profile/platform hints.
7. Project context files such as `AGENTS.md`.
8. Volatile memory, user profile, date, model, and provider lines.

The prompt is stored for the session and replayed byte-for-byte on later turns.
Ephemeral channel/system prompts are appended at API-call time after the cached
system prompt; they must not replace the Tangyuge identity block.

## Included Identity Material

The default identity may include:

- name
- core description
- personality
- system-prompt rules
- small example-dialogue style samples
- constant character-book entries only

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
a = AIAgent(provider="minimax-cn", model="minimax-m3", api_mode="anthropic_messages", quiet_mode=True, platform="qq")
s = a._build_system_prompt_parts()["stable"]
assert s.startswith("# Tangyuge Identity")
assert "You are Hermes Agent" not in s
assert "created by Nous Research" not in s
assert "This is product/runtime guidance, not an identity definition." in s
PY
```
