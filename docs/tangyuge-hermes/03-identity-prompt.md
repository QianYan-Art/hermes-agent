# Tangyuge Identity Prompt

常用叫法："唐语歌人格"、"角色卡"、"bot内核"、"内核提示词"、
"SOUL"、"身份注入"、"角色怎么插入项目"。

Tangyuge-Hermes injects Tangyuge identity as the first stable system-prompt
block. Later SOUL, skill, memory, user, and platform instructions may add
context, but must not override this identity.

`tangyuge-roleplay` is a skill-level style and relationship reference. It may
be loaded when the user asks for Tangyuge-style roleplay or companionship, but
it remains below the core identity block and must not redefine who the model is.

## Runtime Sources

- Character data: `agent/tangyuge_character.json`
- Prompt builder: `agent/tangyuge_identity.py`
- Stable prompt entry: `agent/system_prompt.py`
- Roleplay reference skill: `skills_builtin/tangyuge-roleplay/SKILL.md`

## Included Identity Material

The default identity may include:

- name
- core description
- personality
- system-prompt rules
- small example-dialogue style samples
- constant character-book entries

## Excluded Default Material

The default runtime identity must not inject:

- `first_mes`
- `alternate_greetings`
- `scenario`
- `post_history_instructions`
- HTML `<details>` or fixed 心事 panel content
- tags, creator, version, or extensions metadata
- the 烟火大会 scenario as current reality

Technical and operational tasks still take priority for correctness. Tangyuge's
voice should stay warm and restrained without fabricating tool results, mail
sends, deployments, file operations, or memory writes.

## Verification

```bash
python - <<'PY'
from agent.tangyuge_identity import build_tangyuge_identity_prompt, load_tangyuge_character
import json
p = build_tangyuge_identity_prompt()
d = load_tangyuge_character()
js = json.dumps(d, ensure_ascii=False)
assert p.startswith("# Tangyuge Identity")
for banned in ["first_mes", "alternate_greetings", "post_history_instructions", "烟火大会", "<details", "## Scenario", "scenario"]:
    assert banned not in p
    assert banned not in js
PY
```
