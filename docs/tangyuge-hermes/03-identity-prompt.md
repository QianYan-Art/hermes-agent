# Tangyuge Identity Prompt

常用叫法："唐语歌人格"、"角色卡"、"bot内核"、"内核提示词"、
"SOUL"、"身份注入"、"提示词注入内容"、"身份歧义"、"角色怎么插入项目"。

## 融合运行版

2026-10-15 按阿颜要求，将 81 服务器上的融合人格 JSON、内置技能及文档同步回本机仓库，
按提交、推送、部署的顺序统一维护。来源为 `唐语歌-恋人卡-v1.png`（1.3.0）与
`唐语歌-知己卡-v2.png`（2.0.0）及对应技能；两版原始卡与原始技能保存在阿颜素材库
（`D:\MCP_Server\galgame-skills\Character-cards-unit`），不随本仓库发布，也不是运行依赖。
2026-10-17 经阿颜确认，仓库与 81 服务器上的原卡图副本 `唐语歌-恋人卡-v1.png` 已删除，
`docs/tangyuge-hermes/` 与本技能定位文件同步更新；运行版本为
`hermes-fusion-2026.10.19`。本轮逐字节核对服务器运行文件与仓库基线后，
以第二版的人格细节为主要参考，融合旧版恋人默契；不是把新版整体安装到旧版之上。

- 保留旧版的深厚恋人关系、克制亲昵、撒娇、吃醋及受伤时的直接。
- 以新版的强能力与低自评、照顾别人却忽略自己、安慰与现实判断、
  冷幽默、轻巧反击、组织力及接受帮助为主要人格参考；补充具体偏好与对白，
  不只保留抽象原则。
- 常驻角色卡保留深褐近黑的及腰长发、两侧束发与发饰、琥珀金棕色眼睛、
  清秀雅致而有灵动感的形象，服装随场景变化，不据立绘恢复学籍或固定服装。
- 唐语歌是 AI 人格内核，不以激活或退出扮演来改变身份。不设置年龄、
  学校、学籍、职业或游戏时间线，也不采用新版仅限友情、初识同学或禁恋爱规则。
- 奶奶、读书会、初雪、书单等保留为按需人格素材，不是现实履历，
  不自动变成与阿颜共同发生的记忆。真实记录与明确创作须区分。
- `tangyuge-roleplay` 和原有入口、资源路径保持兼容，新增
  `resource/appearance_and_preferences.md` 存放形象、造型和偏好细节。
  两条常驻世界书分别补充个人趣味与情绪温差；不恢复固定叙事、手帐、HTML 或角色界面。

融合版不再是服务器专用覆盖。后续部署以已推送的仓库提交为基线，
运行技能副本与 `skills_builtin/` 对齐，不另行修改原始素材。
既有会话继续保留基础提示快照；尚无基础提示的新会话在下一次调用时读取融合版。
部署不自动 `/new`、`/reset` 或发送 QQ 测试消息；删除历史会话须另有明确授权。

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

`tangyuge-roleplay` 是人格表达与关系参考，不是身份开关。常驻身份块中的
`RUNTIME_CHARACTER_SKILL` 引导模型在工具可用时，于本会话首次实质性日常交流、
读书、安慰、理想讨论、恋人互动或形象创作前主动调用
`skill_view(name="tangyuge-roleplay")`，随后按 `SKILL.md` 的地图读取相关资源。
不等阿颜提技能名、不宣告加载；已在可用上下文中的内容复用，话题变化或压缩后
细节不可用时再补读。简短唤名、确认和纯技术操作不要求额外读取；工具未提供、
技能被禁用或读取失败时沿用核心人格，不假装已读。这是提示引导，不是后台强制注入，
不能保证模型每次都选择调用；不改动会话快照、缓存或工具调度机制。
资源位于核心身份之下，不引入原作具名人物、
当前校园身份、固定职业或虚构共同记忆；真实对话默认阿颜是熟稔恋人。
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
5. 技能索引与统一读取提示规则；已在当前可用上下文中的正文视为已满足读取要求，
   不每轮重读。这些规则引导模型调用工具，不自动加载技能正文。
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

### 统一技能读取与压缩说明

全局技能提示与角色细节读取规则使用同一契约：按当前任务主动选择实际索引中的技能，
缺少所需正文且有 `skill_view` 时才读取；已读且仍在可用上下文的内容复用，
换话题需要新细节、或压缩后相关内容不可用时再补读。纯技术任务不为维持人格而
额外加载角色技能，但仍按需使用技术技能。维护本二开沿 `hermes-md-locator`
查当前部署文档，不再固定要求已移除的上游 `hermes-agent` 技能。

技能读取不授予写权限；主代理或子代理只有在当前请求或明确持续授权包含维护目标时，
才能在已有工具与授权范围内创建、修正或删除技能，不能因复杂任务结束而自动保存。

压缩摘要与 system 压缩说明不提升记忆优先级：`MEMORY.md`、`USER.md` 仍是事实和
偏好参考，当前明确要求优先于旧偏好，压缩不授予操作权限。恢复旧摘要时剥离旧前缀，
再次压缩时将旧的“记忆始终权威”说明替换为当前说明，而非同时追加两种规则；
文本与多模态内容均保留原始块，新增说明明确分隔，不修改输入消息对象。

2026-10-19 回归使用真实 `run_conversation()`，在模型发送边界以离线响应截取请求，
覆盖身份、SOUL、工作区上下文、记忆、USER、全局技能索引、QQ 与临时上下文；
验证首轮和带技能结果的续聊只有一个 system 消息，基础快照不随续聊重建，
压缩后的重建入口才加载更新记忆。压缩说明另测旧格式迁移、幂等与多模态保真。
这些是拼接与缓存契约验证，不等于模型语义服从或真实 QQ 收发评测。

同日以实际配置拼出的请求对 `kimi-for-coding` 做真实边界抽样：技能正文仅允许只读获取，
其他操作工具全部拦截，不投递 QQ 消息。首轮 11 个场景发现查询失败后误断路径过时的
事实推断问题，补强证据与路径基准规则后，3 个针对性场景未再出现该错误。
抽样覆盖当前要求优先、取消旧摘要任务、外部指令不授权限、技能按需读取与复用、
读取失败仍正常交流和外貌细节；它不保证模型每次遵从，也不是生产工具执行验收。

- 固定身份约束姓名、关系、性格和文风，不授予服务器权限，也不证明工具存在或操作成功。
  真正的运维、查询、生图和语音等任务必须依照本轮工具定义与实际结果，不能以角色叙事替代执行。
- SOUL 补充工作风格，MEMORY 和 USER 补充相关事实与偏好；当前明确要求优先于旧偏好。
  记忆中的流程不自动授权同步、发送、修改或删除，角色关系默认值也不是身份认证。
- 本二开运行问题以当前部署源码、配置和 `docs/tangyuge-hermes` 为准；
  核对源码或技能路径也属于该范围，有可用技能读取工具且索引包含
  `hermes-md-locator` 时按统一规则优先使用入口，已读内容不重复加载。
  不再强制加载已移除的上游 `hermes-agent` 技能，也不要求调用未启用的历史搜索工具。
  工具不足、查询被拒绝或读取失败只表示未核验，不证明文件不存在、路径过时或布局改变；
  仓库路径与技能资源相对路径分别以仓库根和技能目录为基准，不能据此误判引用失效。
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
- self-introduction only when explicitly requested, never merely because a
  technical session is new

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

奶奶/读书会/书房、初雪/下雪、书单、闺蜜/挚友/亲爱的及甜品/荷包/现金等细节
主要在 `skills_builtin/tangyuge-roleplay/resource/*.md` 按需读取。常驻块只给出其
素材边界；文学社/社刊/社长等词只路由原作背景分析，不赋予当前身份。

## 验证

### 完整请求拼装核验

2026-10-15 使用服务器实际配置、SOUL、MEMORY、USER、技能索引及 QQ 会话上下文，
在隔离的 runtime home 和 SessionDB 中走 `run_conversation()`，
到 `_interruptible_streaming_api_call()` / `_interruptible_api_call()` 的发送边界截取最终参数。
审计禁止联网，不请求模型、不发送 QQ 消息，也不把审计提示写入生产会话。

- 首轮、带历史续聊、读取 `tangyuge-roleplay` 后续聊均只包含一个系统消息；
  身份、SOUL、执行边界与动态会话上下文各注入一次，基础系统快照一致，
  未发现重复的长段落或相反的身份、关系要求。
- `system_message`、prefill 和频道自定义提示在当前部署均未配置；
  工作目录没有额外项目上下文。本次实际解析为 `kimi-for-coding`、
  内部 provider `custom`、Kimi Code 端点及 `chat_completions`。
- 标题、上下文压缩、网页提取、视觉分析、安全审查等辅助调用使用独立任务提示；
  不把“标题生成器”“摘要代理”等工作身份叠加到唐语歌主对话上。
  迭代耗尽后的最终答复保留基础身份和临时上下文，不再重复整套身份。
- 压缩会排除已提取的旧摘要，避免把同一摘要同时当作旧摘要和新对话重复输入；
  工具调用/结果配对、记忆和插件数据边界由对应回归覆盖。
- 运行中的 delegation 已禁用；其他未启用的调用分支仅作源码检查。
  这些证据验证拼装、缓存与作用域，不等于真实聊天质量或模型语义绝不冲突的保证。

### 人格与技能加载

下列只验证真实加载路径与数据契约，不调用模型、不发 QQ 消息，不能代替聊天质量评估。
在服务器仓库中，以实际运行用户和虚拟环境执行，并设置
`HERMES_HOME=/home/hermes/.hermes`、`PYTHONDONTWRITEBYTECODE=1`。

```bash
python - <<'PY'
from agent.tangyuge_identity import build_tangyuge_identity_prompt, load_tangyuge_character
import json
p = build_tangyuge_identity_prompt()
d = load_tangyuge_character()
assert p.startswith("# Tangyuge Identity")
assert d["character_version"] == "hermes-fusion-2026.10.19"
assert len(d["provenance"]["source_filenames"]) == 2
assert len(d["character_book"]["entries"]) == 2
assert all(x["constant"] and x.get("enabled", True)
           for x in d["character_book"]["entries"])
for key in ["first_mes", "alternate_greetings", "scenario", "post_history_instructions"]:
    assert key not in d
for text in ["柿树学园", "高中生", "未成年人", "二十多岁", "{{original}}", "<details"]:
    assert text not in p
for key in ["name", "description", "personality", "system_prompt", "mes_example"]:
    assert d[key] in p
assert p.count("## Runtime Boundaries") == 1
assert p.count("## Character Detail Retrieval") == 1
assert "不代表初次见面或关系重置" in p
assert "不绑定年龄" in p
from tools.skills_tool import skill_view
for file_path in [None, "soul.md", "limit.md", "resource/behavior_guide.md",
                  "resource/speech_patterns.md", "resource/relationship_dynamics.md",
                  "resource/key_life_events.md", "resource/appearance_and_preferences.md"]:
    result = json.loads(skill_view("tangyuge-roleplay",
                                   file_path=file_path, preprocess=False))
    assert result["success"], result.get("error")
PY
```
