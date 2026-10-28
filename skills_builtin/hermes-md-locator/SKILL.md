---
name: hermes-md-locator
description: 定位二开文档、源码架构、维护风险、人格、模型、媒体、命令审批、忙时消息与辅助服务状态。
---

# Tangyuge-Hermes 文档入口

## 目标

本技能是顶层文档入口，负责把用户的自然说法映射到仓库内的固定文档。服务器上的 bot 读取 repo `docs/tangyuge-hermes/`；本部署现场仓库根目录通常是 `$HERMES_HOME/hermes-agent`，当前工作目录下没有 docs 时先查这个绝对路径。

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
- 抖音服务器登录：`docs/tangyuge-hermes/09-douyin-login.md`
- 抖音作品与草稿：`docs/tangyuge-hermes/10-douyin-publishing.md`
- 源码架构与维护风险：`docs/tangyuge-hermes/11-source-maintenance.md`

本地 KBase 保存人工运维记录；bot 的文档定位源是上述仓库路径。

## 快速路由表

先按用户原话匹配下表；不要凭记忆猜路径。

| 用户常用说法 | 读取文档 |
| --- | --- |
| "源码梳理", "架构地图", "模块职责", "关键调用链", "耦合", "重复逻辑", "源码审查", "维护风险", "旧审批按钮", "辅助路由串线", "插件加载回滚" | `docs/tangyuge-hermes/11-source-maintenance.md`；区分已修复、静态风险与待确认的协议/架构调整，不把本地回归说成已部署或真实平台验收 |
| "抖音", "抖音登录", "抖音扫码", "抖音账号状态", "服务器抖音", "douyin_login", "抖音登录失效", "抖音二维码", "抖音错误恢复" | `docs/tangyuge-hermes/09-douyin-login.md`；明确失效可向本人私聊自动附二维码，活动上传与有效预览不被自动登录打断；验证须本人处理，不清 profile 或自动切号；登录工具不上传、不发布 |
| "命令审批", "命令还要允许", "始终允许", "approvals.mode", "关闭审批", "mcp_reload_confirm", "不回复消息", "无视消息", "忙时消息", "busy_text_mode", "静默排队" | `docs/tangyuge-hermes/07-server-operations.md` 的命令审批与忙时消息；当前81命令审批off、普通忙时文本interrupt；停止会唤醒并拒绝旧审批等待，不清掉已有授权 |
| "上传半小时", "视频总要重传", "长视频超时", "上传后编辑失败", "resume_stage", "短信等待超时", "确认预览过期" | `docs/tangyuge-hermes/10-douyin-publishing.md`；原片上传55分钟、上传编辑总75分钟、完成后预览独立15分钟、短信页面等待30分钟；仅有同页检查点且原job给出恢复指引才resume_stage，不重传，不绕过未知发布防重 |
| "发布后删除原片", "清理两期视频", "published-records", "删视频保留封面", "封面来源视频已删" | `docs/tangyuge-hermes/10-douyin-publishing.md` 的“发布后移除服务器原片”；先核对发布回执与作品列表，原清单移入发布记录、删除服务器视频及空作品目录；封面素材尚存时图库可校验复用，不能把清单当可上传原片，本机原片不动 |
| "第一期发布结果", "第二期发布结果", "第一栞", "第二栞", "ep01发布", "ep02发布", "两期视频已删", "三期服务器原片已删" | `docs/tangyuge-hermes/10-douyin-publishing.md` 首部当前验收状态及“历史验证记录与边界”；区分本人手机确认、平台提交回执与早期记录，不把已删原片的清单说成仍可上传的视频 |
| "3:4封面", "4:3封面", "9:16黑边", "已保存封面", "封面模板", "星栞封面", "Maple Mono", "cover_template.py", "starlibrary_covers", "saved_image", "paired_images", "cover_saved_sources", "cover_import_saved", "cover_pair", "双源配对", "修改已发布封面" | `docs/tangyuge-hermes/10-douyin-publishing.md` 的封面模板与双源配对；可用固定模板、期号及标题生成横竖素材，再分别导入并配对；竖槽3:4、横槽4:3，不把9:16补边说成满版。修改现有作品需当次授权运维，不用发布新条目代替 |
| "OpenFilm 发布", "抖音发布", "抖音草稿", "保存草稿", "序栞", "作品包", "douyin_content", "抖音后台数据", "确认发布", "自动传片", "手动入库", "2 GiB", "plan_id", "参数无效", "封面", "封面库", "封面分类", "复用封面", "cover_library", "cover_reuse", "发布向导", "定时发布", "结果待核实", "抖音短信验证", "发布短信验证", "发布卡在验证码", "douyin_verification" | `docs/tangyuge-hermes/10-douyin-publishing.md`；阿颜手动运行公共上传脚本入库；已有封面先查分类库并翻页，本人选择后为目标作品重绑新ID；收集文案、封面、可见范围和时间，prepare 返回完整 plan_id 供 stage/draft；预览后本人真实 QQ 确认，publish 只传 action；job明确等待短信时douyin_verification传job_id发码，本人同一私聊键入纯文本六位数字，由程序旁路消费并在原页面验证，不用终端窗口、不重传；页面失效inspect_result须核查，不当登录失效或重投；受理不等于网页已核验，不承诺后台自动通知；暂存不等于发布，不保证旧槽持久或手机可见 |
| "流量日报", "Komari", "VPS 流量", "近24小时流量", "komari_traffic_daily" | `docs/tangyuge-hermes/07-server-operations.md` 的“Komari 流量日报”；只运行固定读取命令，不改 Komari/Kuma 或 Telegram |
| "auxmodel", "/auxmodel", "auxmodel 状态", "辅助模型状态", "Tavily 状态", "联网后端", "搜索后端", "提取后端", "TAVILY_API_KEY", "TAVILY_BASE_URL" | 先读 `docs/tangyuge-hermes/07-server-operations.md` 的“Current Runtime Shape”；实现变更再读 `docs/tangyuge-hermes/05-patches-and-rtk.md` |
| "ollama-vision", "ollama_vision", "providers.ollama_vision", "AUXILIARY_VISION_API_KEY", "minimax-cn", "MINIMAX_CN_API_KEY", "退役配置", "旧视觉key", "模型发现机制" | `docs/tangyuge-hermes/07-server-operations.md` 的“Current Runtime Shape”和 `docs/tangyuge-hermes/05-patches-and-rtk.md`；这些标识是退役索引，不是当前配置入口 |
| "MiMo 覆盖", "旧小米模型", "MiniMax 配置清理", "gateway_session_model_overrides.json", "模型配置删了仍在用" | `docs/tangyuge-hermes/07-server-operations.md` 的“Current Runtime Shape”；区分旧文件、实际读取链与进程内覆盖，不凭历史文件断言当前路由 |
| "TTS", "语音风格", "profile", "reference", "scene", "工作站离线", "metadata_path", "参考音频" | `docs/tangyuge-hermes/07-server-operations.md` 的“工作站 TTS 参数” |
| "Kimi 请求头", "User-Agent", "prompt_cache_key", "缓存命中", "cached_tokens", "官方订阅", "OpenCode Go", "x-opencode-session" | `docs/tangyuge-hermes/07-server-operations.md` 的“Kimi Code 请求与缓存” |
| "缓存时间", "缓存多久", "缓存TTL", "prompt_cache_options", "5m", "1h", "5h限额", "额度重置", "68%", "130%" | `docs/tangyuge-hermes/07-server-operations.md` 的“缓存时长与额度窗口”；通用 API 的 TTL 设置不等于 Coding Plan 支持保证，额度倍率不是客户端请求头选项 |
| "自动压缩", "压缩阈值", "90%", "95%", "compression.threshold", "235929" | `docs/tangyuge-hermes/07-server-operations.md` 的“Current Runtime Shape”；区分 token 阈值、独立消息卫生整理条件与上游缓存过期 |
| "k3-256k", "250K还是256K", "探测失败", "retained", "fallback", "切换后窗口不一致" | `docs/tangyuge-hermes/07-server-operations.md` 的模型与上下文命令；实现边界读 `05-patches-and-rtk.md` |
| "memory 路径", "USER 语音参数", "运行记忆对齐", "TTS schema", "262k还是256k", "二进制回显" | `docs/tangyuge-hermes/07-server-operations.md` 的“运行记忆维护”与模型命令说明；身份边界读 `03-identity-prompt.md` |
| "总览", "项目总览", "整体情况", "二开项目", "tangyuge-hermes 是什么", "文档目录" | `docs/tangyuge-hermes/00-overview.md` |
| "记忆写入授权", "更新 nmem", "Serena 记忆", "KBase 能提交吗", "博客同步", ".doc-maintenance" | `docs/tangyuge-hermes/00-overview.md` and `docs/tangyuge-hermes/07-server-operations.md` |
| "提示词拼接链路", "外部记忆注入", "插件上下文", "提示规则更新后保留历史", "/reset 应用新提示词", "角色刷新保留会话" | `docs/tangyuge-hermes/03-identity-prompt.md` and `docs/tangyuge-hermes/07-server-operations.md` |
| "旧备份能删吗", "备份清理", ".bak", "清理前 SQLite 快照", "SSH 备份", "known_hosts.old 能删吗" | `docs/tangyuge-hermes/07-server-operations.md` |
| "部署", "部署文档", "81部署", "81服务器部署", "服务器怎么部署", "靠什么部署", "main分支部署", "服务命令", "旧版本还保留吗", "sparse checkout", "服务器瘦身" | `docs/tangyuge-hermes/01-deployment-81.md` and `docs/tangyuge-hermes/02-trim-plan.md` |
| "精简方案", "删了什么", "保留什么", "保留平台", "保留toolsets", "为什么docs还有这些", "项目裁剪", "README留几个", "README.zh-CN", "CLI裁剪", "removed commands", "honcho/acp/proxy/lsp/kanban/profile", "provider白名单", "bundled provider", "插件白名单", "插件要不要删", "物理插件清理", "optional deps", "依赖精简", "aiohttp", "QQBot WebSocket依赖", "core dependency", "scripts删除", "google_meet", "teams_pipeline", "精简版测试", "测试基线", "run_trimmed_tests", "trimmed_manifest", "上游残留测试" | `docs/tangyuge-hermes/02-trim-plan.md` |
| "安全依赖升级", "依赖漏洞", "OSV", "OSV Scanner", "漏洞扫描", "CVE", "osv-scanner.toml" | `docs/tangyuge-hermes/02-trim-plan.md` and `docs/tangyuge-hermes/06-upgrade-freeze.md` |
| "唐语歌人格", "角色卡", "bot内核", "内核提示词", "提示词注入内容", "身份歧义", "Hermes身份噪音", "SOUL", "SOUL文档", "通用SOUL文档", "Hermes SOUL", "QQBot变体", "SOUL_QQBOT", "SOUL_QQBOT_DM", "SOUL_QQBOT_GROUP", "私聊SOUL", "群聊SOUL", "身份注入", "角色怎么插入项目", "角色卡界面", "固定UI块", "每轮复盘", "状态栏", "好感度", "情绪表", "表情包", "Unicode emoji", "QQ表情", "方括号表情占位符", "害羞/比心" | `docs/tangyuge-hermes/03-identity-prompt.md` and `docs/tangyuge-hermes/07-server-operations.md` |
| "tangyuge-roleplay", "角色扮演skill", "陪聊skill", "唐语歌skill", "角色卡和skill关系", "角色卡输出格式", "QQ回复格式" | `docs/tangyuge-hermes/03-identity-prompt.md` and `docs/tangyuge-hermes/04-built-in-skills.md` |
| "融合人格", "两版角色卡", "恋人卡", "知己卡", "年龄设定", "禁恋爱", "AI人格内核", "服务器融合副本", "原卡图删除" | `docs/tangyuge-hermes/03-identity-prompt.md` 的“融合运行版”；原始两版卡、原始技能在阿颜素材库，不随仓库发布；原卡图副本已于 2026-10-17 从仓库与服务器删除，融合版由仓库统一维护 |
| "角色卡外貌设定维护", "外貌描写被删", "立绘与角色卡对齐", "角色卡精简", "角色细节维护", "第二版人格融合", "主动调用角色skill机制", "技能需要手动开启吗", "appearance_and_preferences" | `docs/tangyuge-hermes/03-identity-prompt.md` 的“融合运行版”与 `docs/tangyuge-hermes/04-built-in-skills.md`；主动调用是按话题的提示引导，不是身份开关或后台强制注入，旧会话提示快照的生效边界读 `03-identity-prompt.md` |
| "AI感重", "人机感", "说话像AI", "短句断句", "标点切碎", "省略号停顿", "语言润色", "示例对话照搬" | `docs/tangyuge-hermes/03-identity-prompt.md` 的“2026-10-20 语言润色”；风格规则在角色卡 `system_prompt` 的【说话方式】和 `tangyuge-roleplay/resource/speech_patterns.md` 的“标点与句子” |
| "全局技能提示", "技能重复读取", "自动总结skills", "自动修改skill", "技能维护授权", "整体提示词拼接", "压缩后记忆优先级", "旧hermes-agent技能" | `docs/tangyuge-hermes/03-identity-prompt.md` 的“统一技能读取与压缩说明”和 `docs/tangyuge-hermes/04-built-in-skills.md` 的“Skill Boundaries”；读取按需复用，写入须明确授权，不恢复已移除技能 |
| "查询被拒绝", "文件不存在", "路径过时", "技能相对路径", "仓库路径基准" | `docs/tangyuge-hermes/03-identity-prompt.md` 的“作用域与数据边界”；查询失败不证明目标缺失，区分仓库根路径和技能内相对路径 |
| "内置skills", "skills列表", "有哪些skill", "六个skill", "只保留六个skill", "humanizer", "creative", "no-bundled-skills", "locator技能", "mail-vps-ops", "技能怎么内置" | `docs/tangyuge-hermes/04-built-in-skills.md` |
| "patch记录", "二开patch", "/new和/reset", "随机tips", "Telegram webhook tip", "/view", "/context", "上下文窗口", "todo压缩", "压缩后todo", "TODO快照", "conversation compression", "关闭自动记忆", "自动总结skills", "异步subagent", "后台subagent", "delegate_task background", "background=true", "max_async_children", "RTK", "typing_indicator", "输入状态", "正在输入", "thinking状态", "SendResult失败分类", "error_kind", "SEND_ERROR_KINDS", "WebSocket closed空转", "QQBot 100% CPU", "provider", "模型路由", "Tavily", "OpenAI-compatible image", "CPA生图旁路", "suyuan.4071253.xyz", "生图", "生图旁路", "生图参数", "图生图", "改图", "局部重绘", "inpaint", "image-to-image", "images.edit", "image_generate", "image_generate参数", "image_generate看不到", "工具清单", "模型工具列表", "schema", "heredoc", "input_image", "input_images", "mask", "input_fidelity", "style", "media_tag", "MEDIA:<path>", "QQBot发图", "QQBot图片发送", "图片发不出去", "主动消息", "主动推送", "event_id", "qq_event_id", "is_wakeup", "qq_is_wakeup", "FRIEND_ADD", "FRIEND_DEL", "C2C_MSG_RECEIVE", "C2C_MSG_REJECT", "GROUP_ADD_ROBOT", "GROUP_DEL_ROBOT", "GROUP_MSG_RECEIVE", "GROUP_MSG_REJECT", "quality", "num_images", "output_format", "background", "moderation", "output_compression", "api_model", "/auxmodel image", "非档位生图模型", "OPENAI_IMAGE_API_KEY", "QQ授权按钮", "允许一次", "始终允许", "拒绝", "新旧行为差异" | `docs/tangyuge-hermes/05-patches-and-rtk.md` and `docs/tangyuge-hermes/07-server-operations.md` |
| "MiniMax", "minimax-m3", "视频链路", "视频阈值", "45 MiB", "图片识别", "媒体路由", "native video", "视频直传", "视频预算" | `docs/tangyuge-hermes/05-patches-and-rtk.md` and `docs/tangyuge-hermes/07-server-operations.md` |
| "CLIProxyAPI", "124 CPA", "NetCup", "Image-2.5", "gpt-image-2.5", "gpt-image-2-codex", "Flare", "Sunburst", "gpt-5.6-luna", "编排模型", "image_model_unavailable", "HTTP200正文错误", "usage", "usage估算", "multipart", "usage.model为空", "编辑费用没记上", "尺寸不一致", "data URL" | `docs/tangyuge-hermes/07-server-operations.md` 的“生图旁路与 Usage”，错误处理另读 `docs/tangyuge-hermes/05-patches-and-rtk.md`；NetCup 仅为迁移前历史入口 |
| "升级冻结", "上游升级", "能不能合并上游", "release规则", "tag规则", "版本冻结" | `docs/tangyuge-hermes/06-upgrade-freeze.md` |
| "/reasoning", "推理强度", "思考深度", "max档位", "reasoning_effort", "会话与全局设置" | `docs/tangyuge-hermes/05-patches-and-rtk.md` and `docs/tangyuge-hermes/07-server-operations.md` |
| "Kimi Code", "kimi-code", "kimi-for-coding", "KIMI_CODE_API_KEY", "当前用什么模型", "默认模型", "换模型", "切模型", "/model", "--global", "provider前缀", "custom前缀", "命名自定义provider", "262144", "256k上下文", "上下文单位", "k是1024还是1000", "512k", "二进制单位", "会话级还是全局", "自动探测覆盖配置", "/model列表是空的", "模型列表看不到", "provider白名单过滤" | `docs/tangyuge-hermes/07-server-operations.md` 的“Current Runtime Shape”“模型与上下文命令的作用域”，实现细节另读 `docs/tangyuge-hermes/05-patches-and-rtk.md` |
| "grok-search", "GROK_MODEL", "grok-4.3-fast", "搜索模型", "x_search", "grok-4.20-reasoning", "搜索用哪个模型" | `docs/tangyuge-hermes/07-server-operations.md`；`grok-search` skill 的 `.env` 与 runtime `x_search` 是两个独立入口，不要混改 |
| "k3.1-pro", "k3.1-pro-highspeed", "K3.1 Pro", "新版Kimi", "仅支持思考", "thinking-only", "api.kimi.ai", "请求签名", "Msh-Request-Signature", "Msh-Request-Timestamp", "X-Msh-Request-Nonce", "原生图片视频" | `docs/tangyuge-hermes/07-server-operations.md` 的“Current Runtime Shape”“K3.1 Pro 新版验证”，实现与边界另读 `docs/tangyuge-hermes/05-patches-and-rtk.md`；不要把开放平台 `kimi-k3.1-pro` 当成订阅请求 ID |
| "视频能不能看", "视频理解", "发视频", "视频传不上去", "Kimi 看视频", "video_url", "视频缓存", "cache/videos", "视频和文件分开", "视频清理", "k3-256k 不支持视频" | `docs/tangyuge-hermes/07-server-operations.md` 的“Current Runtime Shape”，实现与判定另读 `docs/tangyuge-hermes/05-patches-and-rtk.md` |
| "维护手册", "全局状态", "当前状态", "服务器状态", "服务器全局状态", "运行状态", "重启网关命令", "typing_indicator", "输入状态", "正在输入", "thinking状态", "缓存目录", "cache目录", "image_cache", "audio_cache", "video_cache", "document_cache", "cache/documents", "邮件缓存", "session清理", "自动清理session任务", "session cleanup", "retention cleanup", "timer", "memory/user文档", "检查网关" | `docs/tangyuge-hermes/07-server-operations.md` |
| "邮件文档", "邮箱文档", "邮件VPS文档", "邮件集成文档", "邮箱列表", "有哪些邮箱", "列出全部邮箱", "多域名邮箱", "新域名邮箱漏列", "mail.qianyan.me", "sru.edu.kg", "读邮件", "验证码", "验证链接", "附件", "发信", "回复邮件", "转发邮件", "删除邮件" | `docs/tangyuge-hermes/08-mail-vps.md` |

## 组合路由

- “源码梳理、架构地图、职责混杂、维护风险、旧审批按钮、辅助路由串线、插件加载回滚”：先读 `11-source-maintenance.md`；需要行为历史再按模块转 `05-patches-and-rtk.md` 或抖音专题，不把待确认方案当作已实施。

- "流量日报、Komari、VPS 流量、近24小时流量"：读 `07-server-operations.md` 的“Komari 流量日报”，固定脚本返回 `report` 后用 QQ 文字回复；仅汇总公开可见节点，不操作原有 Telegram 日报或告警。

- "auxmodel、/auxmodel、辅助模型状态、Tavily 状态、联网后端、搜索后端、提取后端"：先读 `07-server-operations.md` 的“Current Runtime Shape”，实现变化再读 `05-patches-and-rtk.md`。区分本地配置、key 数和实际在线验证，不因状态查询发起网络探测。
- "ollama-vision、ollama_vision、providers.ollama_vision、AUXILIARY_VISION_API_KEY、minimax-cn、MINIMAX_CN_API_KEY、退役配置、旧视觉key、模型发现机制"：先读 `07-server-operations.md` 的退役说明，再按需读 `05-patches-and-rtk.md`；不要建议重新配置已移除的服务或凭据。
- "提示词拼接链路、外部记忆注入、插件上下文、提示规则更新后保留历史、/reset 应用新提示词、角色刷新保留会话"：先读 `03-identity-prompt.md` 的拼接、作用域和缓存规则；操作前再读 `07-server-operations.md`。不要把重启网关视作旧提示已刷新，不自动执行会话重置。

- "CLIProxyAPI、124 CPA、NetCup、Image-2.5、gpt-image-2-codex、Flare、Sunburst、编排模型、image_model_unavailable、HTTP200正文错误、usage估算、multipart、usage.model为空、编辑费用没记上、尺寸不一致、data URL"：先读 `07-server-operations.md` 的“生图旁路与 Usage”，再按需读 `05-patches-and-rtk.md`。当前入口在 124，NetCup 属迁移前历史；两个精确 2.5 请求可接受 Codex 图片，但不是把无后缀 `gpt-image-2.5` 映射成 Flare。区分请求模型、旁路编排模型和实际执行模型；usage 展示或 HTTP 200 不证明模型可用，不自动切换默认模型。
- "记忆写入授权、更新 nmem、Serena 记忆、KBase 能提交吗、博客同步、.doc-maintenance"：读 `00-overview.md` 的 Documentation And Memory Rules 和 `07-server-operations.md` 的 Documentation Rule；查文档不等于获准写记忆，不混同 Hermes runtime 记忆。
- "旧备份能删吗、备份清理、.bak、清理前 SQLite 快照、SSH 备份、known_hosts.old 能删吗"：先读 `07-server-operations.md` 的 Cleanup Rule；按引用和恢复价值判断，不按后缀或年龄批量删除。
- "/reasoning、推理强度、思考深度、max档位、reasoning_effort、会话与全局设置"：操作与作用域先读 `07-server-operations.md` 的推理强度设置；模型兼容映射再读 `05-patches-and-rtk.md`。
- "全局状态"、"服务器状态"、"当前状态"：先读 `07-server-operations.md`；涉及部署版本或服务来源时再读 `01-deployment-81.md`。
- "维护手册里查重启网关命令"、"重启网关"：读 `07-server-operations.md` 的 Chat-side restart / Chinese operator phrasing。
- "缓存目录"、"cache目录"、"image_cache"、"audio_cache"、"video_cache"、"document_cache"：读 `07-server-operations.md`；涉及部署时哪些目录不该覆盖，再读 `01-deployment-81.md`。
- "自动清理session任务"、"session清理timer"、"retention cleanup"：读 `07-server-operations.md` 的 Session Cleanup Timer。
- "服务器怎么部署、旧版本还在不在、靠什么启动"：读 `01-deployment-81.md` 和 `07-server-operations.md`。
- "服务器瘦身、sparse checkout、为什么服务器没有 tests"：读 `01-deployment-81.md` 和 `02-trim-plan.md`。
- "README留几个、README.zh-CN、为什么只有 README.md"：读 `02-trim-plan.md`。
- "CLI裁剪、removed commands、honcho/acp/proxy/lsp/kanban/profile、provider白名单、bundled provider、插件白名单、插件要不要删、物理插件清理、optional deps、依赖精简、aiohttp、QQBot WebSocket依赖、core dependency、scripts删除、google_meet、teams_pipeline、disabled plugin 为什么还在仓库、精简版测试、测试基线、run_trimmed_tests、trimmed_manifest、上游残留测试"：读 `02-trim-plan.md` 和 `07-server-operations.md`。
- "安全依赖升级、依赖漏洞、OSV、OSV Scanner、漏洞扫描、CVE、osv-scanner.toml"：读 `02-trim-plan.md` 的依赖边界，再读 `06-upgrade-freeze.md` 的安全升级准入规则。
- "我的patch是否内置、/new和/reset差异、/view、/context、上下文窗口、自动记忆/skills总结关闭、typing_indicator、输入状态、正在输入、thinking状态、SendResult失败分类、error_kind、SEND_ERROR_KINDS、WebSocket closed空转、QQBot 100% CPU"：读 `05-patches-and-rtk.md`；涉及服务器当前运行配置再读 `07-server-operations.md`，涉及技能清单再读 `04-built-in-skills.md`。
- "todo压缩、压缩后todo、TODO快照、conversation compression"：读 `05-patches-and-rtk.md` 的上下文压缩与 todo snapshot 行为。
- "生图、图生图、改图、局部重绘、mask、images.edit、image_generate、image_generate看不到、工具清单、模型工具列表、schema、heredoc、media_tag、MEDIA 图片发送、QQBot 发图、图片发不出去、主动消息、主动推送、event_id、qq_event_id、is_wakeup、qq_is_wakeup、FRIEND_ADD、FRIEND_DEL、C2C_MSG_RECEIVE、C2C_MSG_REJECT、GROUP_ADD_ROBOT、GROUP_DEL_ROBOT、GROUP_MSG_RECEIVE、GROUP_MSG_REJECT"：读 `05-patches-and-rtk.md` 和 `07-server-operations.md`；执行生图/改图时直接调用 `image_generate`，不要手写 curl/Python/heredoc。
- "内置skills、skills列表、六个skill、humanizer、creative、no-bundled-skills、上游skill残留"：读 `04-built-in-skills.md`；涉及服务器现场状态再读 `07-server-operations.md`。
- "子代理默认关闭、自动委派、额度消耗、AgentSwarm、Swarm、异步 subagent、后台 subagent、delegate_task background、background=true、max_async_children"：先读 `07-server-operations.md` 的 Delegation runtime，区分当前硬禁用与源码保留能力；需要实现细节再读 `05-patches-and-rtk.md`。定位文档不授权开启子代理或修改禁用配置。
- "/new 或 /reset 出现随机 tip、Telegram webhook tip、tips 从哪里来"：读 `05-patches-and-rtk.md`。
- "MiniMax、视频链路、视频阈值、图片识别、媒体路由"：读 `05-patches-and-rtk.md` 和 `07-server-operations.md`；只问当前服务器状态时先读 `07-server-operations.md`。
- "bot怎么成为唐语歌、角色卡怎么进内核、通用 SOUL 文档在哪里"：读 `03-identity-prompt.md`；涉及运行时文件边界再读 `00-overview.md`。
- "QQBot变体、SOUL_QQBOT、私聊/群聊 SOUL 变体"：读 `03-identity-prompt.md` 的 SOUL 注入规则，再读 `07-server-operations.md` 的运行时清理记录。
- "新建 session 初始提示词、提示词拼接顺序、身份歧义、Hermes Agent 身份噪音、角色卡界面、固定UI块、每轮复盘、状态栏、好感度、情绪表、表情包、Unicode emoji、QQ表情、方括号表情占位符"：读 `03-identity-prompt.md`；涉及当前服务器实际 SOUL、`USER.md` 或表情包目录时再读 `07-server-operations.md`。
- "tangyuge-roleplay、角色扮演skill、陪聊skill、角色卡和skill关系、角色卡输出格式、QQ回复格式"：读 `03-identity-prompt.md` 和 `04-built-in-skills.md`。
- “角色卡外貌设定维护、立绘与角色卡对齐、角色卡精简、第二版人格融合、主动调用角色skill机制”：读 `03-identity-prompt.md` 和 `04-built-in-skills.md`；普通聊天中问长相、发型、偏好或想念，不属于查运维文档，改用 `tangyuge-roleplay` 的相关资源。
- “全局技能提示、技能重复读取、自动总结skills、自动修改skill、技能维护授权、整体提示词拼接、压缩后记忆优先级”：读 `03-identity-prompt.md` 的“统一技能读取与压缩说明”和 `04-built-in-skills.md`；会话快照是否生效另读 `07-server-operations.md`。
- “融合人格、两版角色卡、恋人卡、知己卡、年龄设定、禁恋爱、AI人格内核、服务器融合副本、原卡图删除”：先读 `03-identity-prompt.md` 的“融合运行版”，不把原版校园经历恢复为当前身份。融合版随仓库部署；原始两版卡、原始技能在阿颜素材库，不随仓库发布，原卡图副本已于 2026-10-17 删除，无运行依赖。
- "邮件/邮箱/验证码/附件/邮箱列表/多域名邮箱/新域名邮箱漏列/sru.edu.kg"：读 `08-mail-vps.md`，然后加载 `mail-vps-ops`；查询全部邮箱不加域名或数量过滤，不把服务主机名当作邮箱域名白名单。
- "文档在哪、KBase和服务器文档关系"：读 `00-overview.md` 和 `07-server-operations.md`。

## 触发语义

用户说以下内容时，优先使用本技能：

- “源码梳理”“架构地图”“模块职责”“关键调用链”“耦合”“重复逻辑”“源码审查”“维护风险”“旧审批按钮”“辅助路由串线”“插件加载回滚”

- “流量日报”“Komari”“VPS 流量”“近24小时流量”“komari_traffic_daily”

- “auxmodel”“/auxmodel”“auxmodel 状态”“辅助模型状态”“Tavily 状态”“联网后端”“搜索后端”“提取后端”“TAVILY_API_KEY”“TAVILY_BASE_URL”
- “ollama-vision”“ollama_vision”“providers.ollama_vision”“AUXILIARY_VISION_API_KEY”“minimax-cn”“MINIMAX_CN_API_KEY”“退役配置”“旧视觉key”“模型发现机制”
- “提示词拼接链路”“外部记忆注入”“插件上下文”“提示规则更新后保留历史”“/reset 应用新提示词”“角色刷新保留会话”
- “CLIProxyAPI”“124 CPA”“NetCup”“Image-2.5”“gpt-image-2.5”“gpt-image-2-codex”“Flare”“Sunburst”“gpt-5.6-luna”“编排模型”“image_model_unavailable”“HTTP200正文错误”“usage估算”“multipart”“usage.model为空”“编辑费用没记上”“尺寸不一致”“data URL”
- “记忆写入授权”“更新 nmem”“Serena 记忆”“KBase 能提交吗”“博客同步”“.doc-maintenance”
- “旧备份能删吗”“备份清理”“.bak”“清理前 SQLite 快照”“SSH 备份”“known_hosts.old 能删吗”
- “/reasoning”“推理强度”“思考深度”“max档位”“reasoning_effort”“会话与全局设置”
- “总览”“项目总览”“整体情况”“二开项目”“文档目录”
- “部署文档”“81部署”“81服务器部署”“服务器怎么部署”“靠什么部署”
- “旧版本还保留吗”“main分支部署”“服务命令”
- “精简方案”“删了什么”“保留什么”“项目裁剪”“服务器瘦身”“sparse checkout”“README留几个”“README.zh-CN”“CLI裁剪”“removed commands”“honcho/acp/proxy/lsp/kanban/profile”“provider白名单”“bundled provider”“插件白名单”“插件要不要删”“物理插件清理”“optional deps”“依赖精简”“aiohttp”“QQBot WebSocket依赖”“core dependency”“scripts删除”“google_meet”“teams_pipeline”“精简版测试”“测试基线”“run_trimmed_tests”“trimmed_manifest”“上游残留测试”
- “安全依赖升级”“依赖漏洞”“OSV”“OSV Scanner”“漏洞扫描”“CVE”“osv-scanner.toml”
- “角色卡”“唐语歌人格”“bot内核”“内核提示词”“提示词注入内容”“身份歧义”“Hermes身份噪音”“SOUL”“SOUL文档”“通用SOUL文档”“Hermes SOUL”“QQBot变体”“SOUL_QQBOT”“SOUL_QQBOT_DM”“SOUL_QQBOT_GROUP”“私聊SOUL”“群聊SOUL”“身份注入”“角色卡界面”“固定UI块”“每轮复盘”“状态栏”“好感度”“情绪表”“表情包”“Unicode emoji”“QQ表情”“方括号表情占位符”
- “tangyuge-roleplay”“角色扮演skill”“陪聊skill”“唐语歌skill”“角色卡和skill关系”“角色卡输出格式”“QQ回复格式”
- “融合人格”“两版角色卡”“恋人卡”“知己卡”“年龄设定”“禁恋爱”“AI人格内核”“服务器融合副本”“原卡图删除”
- “角色卡外貌设定维护”“外貌描写被删”“立绘与角色卡对齐”“角色卡精简”“角色细节维护”“第二版人格融合”“主动调用角色skill机制”“技能需要手动开启吗”“appearance_and_preferences”
- “全局技能提示”“技能重复读取”“自动修改skill”“技能维护授权”“整体提示词拼接”“压缩后记忆优先级”“旧hermes-agent技能”
- “内置skills”“skills列表”“有哪些skill”“六个skill”“只保留六个skill”“humanizer”“creative”“no-bundled-skills”“locator技能”“技能怎么内置”
- “patch记录”“二开patch”“/new和/reset”“随机tips”“Telegram webhook tip”“/view”“/context”“上下文窗口”“todo压缩”“压缩后todo”“TODO快照”“conversation compression”“关闭自动记忆”“自动总结skills”“异步subagent”“后台subagent”“delegate_task background”“background=true”“max_async_children”“RTK”“typing_indicator”“输入状态”“正在输入”“thinking状态”“SendResult失败分类”“error_kind”“SEND_ERROR_KINDS”“WebSocket closed空转”“QQBot 100% CPU”
- “生图”“生图旁路”“图生图”“改图”“局部重绘”“mask”“images.edit”“image_generate”“image_generate看不到”“工具清单”“模型工具列表”“schema”“heredoc”“input_image”“input_images”“input_fidelity”“style”“media_tag”“MEDIA图片发送”“QQBot发图”“QQBot图片发送”“图片发不出去”
- “MiniMax”“minimax-m3”“视频链路”“视频阈值”“45 MiB”“图片识别”“媒体路由”“native video”“视频直传”“视频预算”
- “Kimi Code”“kimi-code”“kimi-for-coding”“KIMI_CODE_API_KEY”“默认模型”“当前用什么模型”“换模型”“切模型”“/model”“--global”“命名自定义provider”“262144”“上下文单位”“k是1024还是1000”“512k”“会话级还是全局”“自动探测覆盖配置”“/model列表是空的”“模型列表看不到”
- “grok-search”“GROK_MODEL”“grok-4.3-fast”“搜索模型”“x_search”“grok-4.20-reasoning”
- “视频能不能看”“视频理解”“发视频”“视频传不上去”“Kimi 看视频”“video_url”“视频缓存”“cache/videos”“视频和文件分开”“视频清理”
- “k3.1-pro”“k3.1-pro-highspeed”“K3.1 Pro”“新版Kimi”“仅支持思考”“thinking-only”“api.kimi.ai”“请求签名”“Msh-Request-Signature”“Msh-Request-Timestamp”“X-Msh-Request-Nonce”“原生图片视频”
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
- “邮箱列表”“有哪些邮箱”“列出全部邮箱”“多域名邮箱”“新域名邮箱漏列”“mail.qianyan.me”“sru.edu.kg”
- “验证码”“验证链接”“邮件附件”“发邮件”“回复邮件”“转发邮件”“删邮件”
- “按维护手册处理”“按全局状态文档核对”
- “之前做了什么 patch”“当前有哪些补丁”“更新时要保留什么”
- “tangyuge-hermes 二开”“二开方案”“部署方案”“当前 mission 方案”

## 使用规则

1. 用户问“维护手册、如何维护、如何重启、如何删除 skill、如何改配置、日常操作步骤”时，读取 `docs/tangyuge-hermes/07-server-operations.md`。
2. 用户问“全局状态、当前状态、服务器状态、网关状态”时，读取 `docs/tangyuge-hermes/07-server-operations.md` 和 `docs/tangyuge-hermes/01-deployment-81.md`。
3. 用户问“邮件 VPS、邮箱列表、多域名邮箱、新域名邮箱漏列、sru.edu.kg、读邮件、附件、发信、回复、转发、Trash、删除、邮件 skill”时，读取 `docs/tangyuge-hermes/08-mail-vps.md`。
4. 用户问“更新、diff、patch、当前真实配置、启用工具集、provider、模型、memory、skills”时，读取 `docs/tangyuge-hermes/05-patches-and-rtk.md`、`docs/tangyuge-hermes/07-server-operations.md` 和相关专题文档。
5. 用户问 tangyuge-hermes 二开、部署方案、当前实现边界时，优先读取本技能列出的 repo 文档。
6. 用户问表内没有的新主题时，按 repo docs 的标题、常用叫法和正文关键词定位；不要因为路由表没有列出就回答“没有文档”。
7. 不要凭记忆猜路径；先使用上面的 repo 固定路径。
8. 文档和当前仓库/服务器状态冲突时，必须说明“文档可能过期”，再建议现场核验命令。

## 注意事项

- 不要把 API key、bot token、私钥内容输出给用户。
- 本技能只定位和读取文档；真正修改服务器、重启网关、清理文件前，仍要按 repo 文档和当前现场状态逐项核对。
- 每次 repo `docs/tangyuge-hermes/` 或 README 增删主题、改常用叫法、改当前运行状态时，都要检查并同步更新本技能的 description、快速路由表、组合路由和触发语义。
