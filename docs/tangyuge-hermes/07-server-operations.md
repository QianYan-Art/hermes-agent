# Server Operations

This is the bot-facing operations reference for Tangyuge-Hermes on the 81
server. It replaces the old home-directory lookup documents.

## Source Of Truth

常用叫法："维护手册"、"全局状态"、"服务器全局状态"、"当前状态"、
"重启网关命令"、"自动清理session任务"、"session清理timer"、
"/reasoning"、"推理强度"、"思考深度"、"max档位"、"会话与全局设置"。

- Code: `/home/hermes/.hermes/hermes-agent`
- Runtime home: `/home/hermes/.hermes`
- Virtual environment: `/home/hermes/.hermes/venvs/hermes-agent`
- Service: `hermes-gateway.service`
- Service command: `/home/hermes/.hermes/venvs/hermes-agent/bin/hermes gateway run`
- Repo docs: `/home/hermes/.hermes/hermes-agent/docs/tangyuge-hermes/`
- Server checkout mode: sparse-checkout runtime tree; tests and development
  artifacts stay in local/GitHub `main` but are excluded on the server.

Do not keep separate home-directory lookup docs. `hermes-md-locator` should
route project, server, maintenance, and mail-documentation questions to repo
docs.

## Current Runtime Shape

抖音服务器登录的独立插件、工具边界、扫码与验证操作见
`09-douyin-login.md`；作品手动入库、封面、stage、草稿及逐次确认发布见
`10-douyin-publishing.md`。登录工具本身不上传或发布；统计仅限网页可靠可见字段，
不是官方 API。不要把浏览器 profile、有效原片和防重账本当成无用缓存清理。
UTC 2026-10-26 第一栞提交发布并核对列表后，已按阿颜明确要求删除服务器 `ep00/ep01`
原片，原清单转入 `/var/lib/hermes-douyin/published-records/`；本机原片、封面库、
profile与防重记录保留。该目录只供图库校验，不能代替可上传原片，详见抖音专题。

Default model provider:

- Provider slug: `kimi-code`（`providers:` 下的命名自定义 provider，运行时
  解析出的内部 provider 名是 `custom`）
- Display name: `kimi-code`
- Base URL: `https://api.kimi.com/coding/v1`
- Default model: `k3.1-pro`（2026-10-23 从 `kimi-for-coding` 切换）
- Key env: `KIMI_CODE_API_KEY`（值只存 runtime `.env`，不入仓库和文档）
- Transport: 显式 `chat_completions`。必须显式写，否则 URL 自动检测会把
  `/coding` 当成 Anthropic 协议。
- Context length: 全局 `model.context_length` 为 `262144`。
  `k3-256k` 的官方 `/models` 在 2026-09-16 返回 `262144`，即二进制 `256K`。
  `providers.kimi-code.models.k3.1-pro.context_length` 单独设为
  `262144`，保留原运行窗口；本轮 `/models` 对 `k3.1-pro` 自报 1048576，
  不自动扩大配置窗口，旧模型的独立窗口配置仍保留。
  注意窗口只认 per-model 的 `models.<model>.context_length`，
  **不认** provider 顶层的 `context_length`。
- `agent.reasoning_effort` 全局为 `low`（2026-10-23 按本人最新要求设置；切换前现场为 high）。Kimi 的思考参数由
  `plugins/model-providers/custom/` 的 Kimi Code 分支发出：
  `extra_body.thinking.type` 为 `enabled`/`disabled`，并映射
  `minimal|low -> low`、`medium|high -> high`、`xhigh|max -> max`。
  `k3.1-pro` / `k3.1-pro-highspeed` 仅支持思考模式，显式关闭时本地拒绝请求。
  该分支只匹配主机 `api.kimi.com` 或 `api.kimi.ai` 且路径为 `/coding` 或 `/coding/v1`，
  其他自定义 provider 行为不变。
- `minimax-cn` CN API-key provider 已退役：配置、`MINIMAX_CN_API_KEY`、
  认证入口、模型目录和专属“不自动发现模型”逻辑已移除。
  2026-10-15 复核当前运行配置、认证和 `.env`，国际 MiniMax 同样未配置、
  未保存凭据。国际 `minimax` 和 `minimax-oauth` 的通用协议支持不等于启用配置。
- The old main-model custom providers `openrouter`, `siliconflow`,
  `deepseek-direct`, and `xiaomi-token-plan-cn` are not used on the 81 runtime.
  生图与 TTS 设置独立，本轮保持不变；旧 `providers.ollama_vision` 配置及
  `AUXILIARY_VISION_API_KEY` 专属凭据已移除，不再经过独立 Ollama 视觉服务。
  这些退役标识仅用于检索迁移说明，不是可恢复使用的当前配置入口。
- 旧 `gateway_session_model_overrides.json` 是历史残留，当前代码没有加载它；
  不能仅凭文件内容声称活动会话仍在使用 MiMo。清理退役服务时须同时检查
  配置、认证、环境、网关内存覆盖及模型目录缓存，不能只删除 `providers:` 条目。
  2026-10-15 已删除该旧文件、`provider_models_cache.json`、旧
  `cache/model_catalog.json` 和停留在 5 月的 `qqbot_gateway_status.json`，
  重启后核对进程环境及真实模型解析，默认仍为 Kimi Code。
  当前连接状态以 `gateway_state.json` 的 QQ platform 状态为准。
  通用公开模型目录重新获取后可能包含厂商名称，不代表配置了相应服务或凭据。
- `DEEPSEEK_API_KEY` may remain in `.env` as a fallback key, but the default
  main model does not use it.
- `prompt_caching.cache_ttl` is `5m`。该缓存语义是 Anthropic 兼容路径
  （`cache_control` 标记 + 5 分钟续期）的行为；Kimi Code 走
  `chat_completions`，不适用这条 Anthropic 缓存路径。
- 自动 token 压缩阈值按本轮要求从 `compression.threshold: 0.95` 调整为
  `0.90`；主模型仍为 `k3.1-pro`、`low`、262144。触发线为
  `int(262144 * 0.90) = 235929`，不是只计算用户正文；压缩目标比例 `0.15`、
  首尾保护 3/12 条、400 条消息的卫生整理上限保持不变，后者是独立触发条件。
- `agent.image_input_mode` 为 `auto`，没有独立辅助视觉配置，QQ 图片直接交给
  本会话的 Kimi 主模型。图片使用 OpenAI 兼容 `image_url` base64 data URL。
  路由基于 `_resolve_session_agent_runtime()` 的模型、provider 和真实端点，
  会话 `/model` 切换生效，不受其他会话的进程全局状态影响。
  显式 `supports_vision: false`、`image_input_mode: text` 或独立视觉覆盖仍优先。
- QQ videos are routed independently from images. 能否内联上传由
  `agent/image_routing.py` 的 `supports_native_video_input()` 判定，目前有两条
  实现路径：
  - 国际 MiniMax：provider 为 `minimax` 且模型名以 `minimax-m3`
    开头，视频作为 Anthropic 兼容的原生 `video` block 上传。
  - Kimi Code：HTTPS 官方端点为 `api.kimi.com` 或 `api.kimi.ai` 的
    `/coding` 或 `/coding/v1`，且模型是
    `k3.1-pro`、`k3.1-pro-highspeed`、`kimi-for-coding`、`kimi-for-coding-highspeed` 或 `k3`，视频作为
    OpenAI 兼容的 `video_url` base64 data URL 上传，与图片同形。
    **`k3-256k` 按官方模型对比表不支持视频**，不在名单内。
  命名自定义 provider 运行时解析成 `custom`，所以 Kimi 这条靠 base_url 识别，
  相似主机名不会误命中。不在名单内的模型回落到缓存路径文本标记。
  内联预算两条路径共用：单文件 45 MiB、单轮合计 45 MiB，超出即回落。
  2026-10-23 已对 `k3.1-pro` 执行真实文本、图片、原生视频与自动工具续轮 HTTP 验收。
  高速版及名单中其他模型没有在这轮逐一实测；HTTP 验收不代表真实 QQ 投递通过。
- Kimi 官方能力依据：`https://www.kimi.com/code/docs/kimi-code/models.html`；
  请求内容类型对应官方 kimi-cli 的 `ImageURLPart` / `VideoURLPart` 适配器。
- `/auxmodel` 显示本会话主模型媒体能力、生图与 TTS 配置，以及搜索和提取实际
  选择的后端。主模型视觉通过 `/model` 切换，未配置独立视觉时不会创建辅助覆盖。
  生图/TTS 仍可用 `/auxmodel image|tts <model>` 只切模型名。
  OpenAI 生图状态显示解析后的请求模型和独立 `quality`。切换非档位模型时
  更新 `image_gen.openai.api_model`、保留原质量档位；切回档位会清除旧请求覆盖。
  `OPENAI_IMAGE_API_MODEL` / `OPENAI_IMAGE_MODEL` 的环境优先级不变。
- Tavily 的 `TAVILY_API_KEY` 只放 runtime `.env`，可用逗号或换行分隔多个 key；
  请求轮换首选 key，认证、限额、服务或连接失败时按请求实现依次回退。
  `TAVILY_BASE_URL` 可覆盖默认 `https://api.tavily.com`。
  `/auxmodel` 只显示配置与 key 数，不显示密钥、不发请求，不把已配置当成联网验证通过。
- 四类入站媒体各有独立缓存目录和各自的清理，互不混用：

  | 类型 | 目录常量 | 清理函数 |
  |---|---|---|
  | 图片 | `IMAGE_CACHE_DIR` | `cleanup_image_cache()` |
  | 语音 | `AUDIO_CACHE_DIR` | `cleanup_audio_cache()` |
  | 视频 | `VIDEO_CACHE_DIR` | `cleanup_video_cache()` |
  | 文件 | `DOCUMENT_CACHE_DIR` | `cleanup_document_cache()` |

  四个清理都挂在 cron ticker 上，每小时扫一次，保留 24 小时。目录常量由
  `get_hermes_dir(新路径, 旧路径)` 解析：**旧布局目录存在就继续用旧的**，
  所以 81 上是混合布局——图片和语音在 `~/.hermes/image_cache/`、
  `~/.hermes/audio_cache/`，视频和文件在 `~/.hermes/cache/videos/`、
  `~/.hermes/cache/documents/`。这是兼容行为，不需要迁移。
- 这四个目录另有一层兜底：服务器本地的 `/etc/cron.weekly/hermes-cache-cleanup`
  每周日 06:47 按 `audio_cache` 7 天、`image_cache` 14 天、`cache/videos` 7 天、
  `cache/documents` 14 天清理（另含 `logs` 30 天）。网关正常运行时 24 小时那一层
  更激进，文件活不到这些门槛，兜底只在网关长时间停止时才真正触发。该脚本按当前
  混合布局写死路径，且**不在本仓库内**，布局变化时要单独同步。
- QQ 语音和视频此前都会落进文档缓存。现在 `video/*` 附件走
  `cache_video_from_bytes()`，语音的三条路径（转换成功、转换失败回退、异常回退）
  统一走 `cache_audio_from_bytes()`。QQ 把普通文件上传标记为 `file`，这类即使
  扩展名像视频或音频也仍按文件进文档缓存，与 `_process_attachments()` 决定是否
  进 `video_urls` 的判据一致。
- 邮件的两个缓存目录 `cache/mail_attachments/` 和
  `cache/mail_verification_links/` 不在上述四类里，gateway 的清理不覆盖它们，
  由 `mail_vps_fetch.py` 每次调用时按配置的 `retention_hours` 自行回收。
- Built-in API-key provider env discovery is disabled by default. Do not set
  `HERMES_BUILTIN_ENV_PROVIDER_DISCOVERY=1` on the 81 deployment unless the
  intent is to restore legacy built-in provider auto-listing from env vars.
- Bundled main-model provider discovery is allow-listed to `custom`,
  `deepseek`, and `minimax`. The expected provider registry is `custom`,
  `deepseek`, `minimax`, and `minimax-oauth`.
- `/home/hermes/.hermes/SOUL.md` is a style-only overlay. It must not contain
  `You are Hermes Agent`, `created by Nous Research`, or any other identity
  definition. `agent/prompt_builder.py` normalizes the old default SOUL identity
  template at load time as a second safety net.
- Old runtime QQBot SOUL variants `SOUL_QQBOT_DM.md` and
  `SOUL_QQBOT_GROUP.md` were confirmed unused and removed. Current runtime
  prompt injection reads only `/home/hermes/.hermes/SOUL.md`.

Retained toolsets:

- `browser`
- `clarify`
- `cronjob`
- `delegation`
- `file`
- `image_gen`
- `memory`
- `messaging`
- `skills`
- `terminal`
- `todo`
- `tts`
- `vision`
- `web`

Delegation runtime:

- 2026-10-25 核验：服务器 `agent.disabled_toolsets` 包含 `delegation`，
  当前会话主模型不应获得 `delegate_task`。上方 retained 列表表示源码保留能力，
  不表示运行时全部启用；不存在 Kimi CLI 的 Agent／AgentSwarm 或 Swarm 模式。
- 普通回合的自动记忆／技能审查仍关闭；SOUL、MEMORY 和 USER 未发现自动委派规则。
- 若以后按用户明确要求重新启用 delegation，静态和动态工具说明都要求当前任务明确授权，
  不以任务复杂、可并行或技能要求审查为理由自动派发，不通过终端或外部CLI绕过。
  这是工具提示约束；当前硬边界仍是禁用工具组，不是自然语言授权识别器。
- 源码保留 `delegate_task(background=true)` 单任务异步能力，完成结果由网关回到原会话；
  当前禁用配置下不可用。明确请求本身不会自动修改服务器禁用列表。
- `delegation.max_async_children` defaults to `3`; new background subagent
  dispatches are rejected at capacity instead of queued.

Enabled built-in skills:

- `grill-me`
- `grok-search`
- `hermes-md-locator`
- `mail-vps-ops`
- `paper-translation-to-docx`
- `tangyuge-roleplay`

The server runtime directory `/home/hermes/.hermes/skills` should contain only
these six directories. Legacy upstream bundled skills such as `humanizer` and
`creative` have been removed from the runtime and ignored server checkout. The
guard file `/home/hermes/.hermes/.no-bundled-skills` prevents bootstrap code
from repopulating the upstream bundled skill catalog.

Supported platform surface is narrowed to QQBot, API server, CLI, and cron.
Removed command/platform/tool surfaces should stay removed unless a later
mission explicitly reintroduces them.

QQBot gateway WebSocket support depends on the repo's core `aiohttp` pin. The
adapter imports `aiohttp` directly for `ClientSession`, WebSocket message types,
and proxy-aware `ws_connect`; a clean 81-style install must not depend on an
old server-local package left in the venv.

Removed top-level CLI commands fail closed with a Tangyuge-Hermes message:
`proxy`, `lsp`, `portal`, `kanban`, `curator`, `insights`, `claw`, `acp`,
`profile`, `honcho`, `dashboard`, `desktop`, and `gui`. The `memory` command is
narrowed to `status`, `off`, and `reset`.

README policy:

- `README.md` is the only repository README.
- Do not restore `README.zh-CN.md`; it previously carried upstream marketing
  and non-retained platform claims.

Repository security scanning is CI-only: `.github/workflows/osv-scanner.yml`
invokes `--config=osv-scanner.toml` for lockfile checks. That TOML file is
tracked with the checkout and is not server runtime data or a replacement for
upgrading a vulnerable retained dependency.

Plugin policy:

- The 81 runtime enables `rtk-rewrite` in `plugins.enabled`, and the active
  runtime plugin now resolves to the bundled `plugins/rtk-rewrite/` copy. The
  old `/home/hermes/.hermes/plugins/rtk-rewrite/` user override was removed
  after verifying it was byte-identical to the bundled plugin.
- The server binary `/home/hermes/.local/bin/rtk` is at `0.49.0`, updated on
  2026-09-16 from `0.48.0`. The Linux x86_64 musl archive was verified against
  SHA256 `7278231dfd7e6a730a4ab7f847b195bcf02289c2d57622b0dab75a6411100c8f`
  before install; the file stays owned by `hermes:hermes` with mode `755`.
  升级方式：从 `rtk-ai/rtk` 的 release 取
  `rtk-x86_64-unknown-linux-musl.tar.gz`，本地校验 SHA256 后再上传替换——81
  直连 GitHub 不稳定，不要在服务器上直接跑官方 install.sh。旧二进制按
  `rtk.bak-<时间戳>` 留在同目录，确认无误后删除。
- 本次已验证实际 `pre_tool_call` 注册、命令改写、已有 `rtk` 前缀的幂等处理、
  不支持命令的透传和只读 Git 执行。成功改写返回码仍为 `3`，透传为 `1`，
  与现有插件兼容，不需要新增工具、恢复 user override 或运行 `rtk init`。
- Bundled plugin discovery is allow-listed to retained web/browser/image/RTK
  surfaces: `browser/browser_use`, `browser/browserbase`,
  `browser/firecrawl`, `web/exa`, `web/firecrawl`, `web/parallel`,
  `web/tavily`, `image_gen/openai`, `rtk-rewrite`, `disk-cleanup`, and
  `security-guidance`.
- Image generation uses the `image_gen/openai` provider against an
  OpenAI-compatible Images API endpoint. Keep endpoint URL in
  `image_gen.openai.base_url`; on the 81 runtime this is
  `https://suyuan.4071253.xyz/v1`. Keep the secret in
  `OPENAI_IMAGE_API_KEY`.
  The default API model sent to the endpoint is `gpt-image-2`. The visible
  `gpt-image-2-low`, `gpt-image-2-medium`, and `gpt-image-2-high` names are
  Hermes quality tiers; a non-tier `/auxmodel image <model>` value is treated
  as the actual Images API model sent to the endpoint. The `image_generate`
  tool can control `quality`, `num_images`, `output_format`, `background`,
  `moderation`, `output_compression`, `style`, and a non-tier `model` /
  explicit `api_model` override for text-to-image when the active provider
  supports those fields. It also supports image-to-image and local edits via
  `input_image`, `input_images`, `mask`, and `input_fidelity`; local paths,
  `file://` URLs, HTTP(S) URLs, and data URLs are accepted for source/mask
  images and are uploaded through the OpenAI SDK `images.edit` path.
  `output_compression` is valid only with `output_format=jpeg` or
  `output_format=webp`; the current bot-facing tool does not expose streaming
  partial image events.
  Because this runtime explicitly sets `image_gen.provider: openai`,
  `image_generate` must appear in the model-visible tool list even if the
  provider has a transient credential or dependency problem. Those failures
  belong in the tool result as `auth_required`, `provider_not_registered`, or
  provider-specific errors; the model should still call `image_generate`
  directly instead of creating curl/Python/heredoc scripts.
- Bot image-generation requests should use `image_generate` directly. The tool
  returns cached local image paths with `media_tag` (`MEDIA:<path>`), and
  `gateway/run.py` auto-appends current-turn `image_generate` media tags when
  the final reply omits them. QQBot `send_message` media delivery uses the
  running QQBot adapter's native HTTP `POST` upload path; without that live
  adapter, the tool returns an explicit text-only REST-path error instead of
  dropping the attachment. Live adapter uploads and generic live-adapter
  `send()` calls are scheduled back onto the gateway-owned event loop so they
  do not fail with cross-loop `is bound to a different event loop` errors. QQ
  text/media sends can also use explicit event-based send context through
  `qq_event_id`, and QQ C2C sends can request `qq_is_wakeup`. On the current
  runtime, C2C native media still reuses the latest inbound message ID as a
  passive fallback only when no explicit `qq_event_id` / `qq_is_wakeup`
  context is present.
- When a QQ voice reply already contains tool-generated audio
  (`[[audio_as_voice]]` or audio `MEDIA:<path>`), the gateway sends that media
  through the normal media delivery path and does not generate a second
  runner-side auto-TTS reply.
- Platform config can set `typing_indicator: false` to disable the generic
  typing/thinking refresh loop for that platform while preserving reply
  delivery. The default remains `true`.
- QQ text/media send failures include both the human-readable `error` and a
  stable `SendResult.error_kind` category (`too_long`, `bad_format`,
  `forbidden`, `not_found`, `rate_limited`, `transient`, or `unknown`). The QQ
  WebSocket reader also raises immediately if the stored WebSocket is already
  closed, so reconnect/backoff logic handles that state instead of a tight
  read-loop retry.
- On the current 81 runtime, active generated-image and TTS files still land in
  `/home/hermes/.hermes/image_cache/` and `/home/hermes/.hermes/audio_cache/`
  because those legacy directories already exist on that host. The shared
  `/home/hermes/.hermes/cache/` 下，`documents/` 保存 QQ 普通文件，
  `videos/` 保存 QQ 入站视频，邮件缓存单独由 helper 管理。
- QQBot daily expression supports two practical paths: Unicode emoji directly
  in text, or existing local sticker/image files under
  `/home/hermes/.hermes/emojis/` sent with `MEDIA:/absolute/path`. Bracketed
  placeholders such as `[害羞/比心]` are plain text on QQ and should not be used
  as a sticker-sending mechanism. The current QQBot adapter sends text,
  markdown, and native media files; it does not expose QQ native face-ID
  sending.
- QQBot支持命令审批按钮；当前81已按阿颜要求关闭命令审批，配置见下节。
  手动模式下，“始终允许”只持久批准当前规则，不等于关闭所有审批；Tirith动态告警
  还可能仅保存会话授权。旧按钮对应的等待项取消后不能再次放行命令。
- `hermes plugins list --plain` should list only `disk-cleanup`,
  `rtk-rewrite`, and `security-guidance`.
- Retained web/browser plugin shims may remain in the repo even though they are
  not standalone plugins, because retained `web` and `browser` toolsets import
  those provider modules directly.
- Non-retained model provider packages and non-OpenAI image provider packages
  are physically removed from the tracked source after retained-scope tests
  prove they are no longer referenced.

## 命令审批与忙时消息

2026-10-26，当前81使用以下持久运行配置，由官方 `hermes config set` 写入：

```yaml
approvals:
  mode: "off"
  destructive_slash_confirm: false
  mcp_reload_confirm: false
display:
  busy_text_mode: interrupt
```

命令守卫不再等待人工“允许一次/始终允许”，跨新会话及服务重启生效；配置文件中
未加引号的 `off` 可能被YAML读成布尔false，审批解析器同样识别为off。已有永久授权
保留，不用继续点击旧按钮。硬性禁止的灾难性命令和操作系统权限仍按原规则处理，
公开发布等工具自身的真实本人确认不由命令审批开关代替。

普通忙时文本原本默认静默排队，当前改为中断当前模型轮次、优先处理新消息。
正在执行且不检查中断的工具仍须等其返回；`/queue`仍是显式排队，后台抖音上传任务
不会因QQ轮次结束或普通追问被取消。工具说明要求先直接回答用户的进度或是否重传问题，
不以terminal sleep和长轮询占住对话。

明确停止运行会取消pending审批并唤醒阻塞线程，旧按钮无法放行该命令；已有会话批准、
永久批准及YOLO选择不因取消等待被顺带清除。新会话边界仍走原有完整安全状态清理。

## Komari 流量日报

用户说“流量日报”时，运行固定只读命令，把返回 JSON 的 `report` 用正常 QQ
文字回复给用户；`ok=false` 如实报错，不编造流量：

```bash
/home/hermes/.hermes/venvs/hermes-agent/bin/python /home/hermes/.hermes/hermes-agent/scripts/komari_traffic_daily.py
```

面板地址只存在 runtime `~/.hermes/komari_traffic.toml` 的 `base_url`，不放密钥，
不接受模型传入 URL、命令或主机。脚本只读 `/api/nodes` 和 RPC
`public:queryMetrics`，将 `traffic.up` / `traffic.down` 按 `sum` 汇总为近 24 小时
报表，时间范围明确标注 UTC。当前接口可见 12 个节点；不冒称包含私有隐藏节点。
无采样节点标注数据不足，不记为零。

不需要 SSH key，也不新增公网服务、skill、定时器或通用管理工具。
仅在 Hermes runtime `MEMORY.md` 添加一条固定命令用法，不写维护侧记忆。
Komari 原有 Telegram 日报、告警和配置不变；RackNerd 上的 Uptime Kuma 是另一个
独立服务，本功能完全不修改它。

## 生图旁路与 Usage

2026-09-09（UTC）核对的 81 配置：`image_gen.provider=openai`，
`image_gen.model` 和 `image_gen.openai.model` 均为 `gpt-image-2-medium`；
实际请求 `api_model=gpt-image-2`、`quality=medium`。
`image_gen.openai.base_url=https://suyuan.4071253.xyz/v1`，
`image_gen.openai.timeout=180`。图片专用密钥在 `OPENAI_IMAGE_API_KEY`，
现场未设置其他图片模型环境覆盖；不将密钥写入仓库或文档。

当前请求从 EdgeOne 经 124 的 Caddy 和 systemd 网桥 relay，
到 `cliproxyapi-edge-proxy`（回环 59999），
图片转交 `cliproxyapi-image-proxy`（60001），普通模型请求转交 CLIProxyAPI（59998）。
旁路使用 ChatGPT Codex 后端，内部编排模型是 `gpt-5.6-luna`；它不是图片工具
模型，也不是 Hermes 主聊天模型。官方 Images API 的模型支持不等于该账号通道权限。

旁路请求名和执行边界：

- CPA 未显式指定型号时和 `gpt-image-2` 使用 Image-2；
  `gpt-image2` 是同一模型的兼容别名。这不覆盖 Hermes 显式配置的 Flare 请求。
- `gpt-image-2.5-flare`、`gpt-image-2.5-sunburst` 保留同名请求；
  `gpt-image-2.5` 不是旁路接受的便利别名，与未知名称一样返回 HTTP 400。
- 2026-10-15 阿颜明确允许两个 2.5 请求接收终态 `gpt-image-2-codex`。
  原严格校验因此拒绝图片的问题由
  `ops/cliproxyapi-image-proxy/codex-image-compat.patch` 局部修复；
  应用前必须核对源码基线并执行 `git apply --check`，流程见同目录 README。
  不忽略其他型号不匹配、缺少终态、空图或上游真实错误，也不将 Codex 图宣称为
  真正执行了 2.5。Hermes 本身不根据有效响应中的不同模型名拒图。
  本轮默认请求目标使用 `image_gen.openai.api_model=gpt-image-2.5-flare`，
  `model` 继续保留原 `gpt-image-2-medium` 质量档位，其余参数不变。
- 文生图和编辑支持 `n=1..10`；`response_format=url` 返回 data URL，不是图床链接。
  `variations` 只有入口路由与鉴权覆盖，图片旁路未实现该功能。
- 入口先鉴权再读取大图片；缺失或错误密钥返回 401。超过 10 秒保活后，
  后续失败可能表现为 HTTP 200 加 `error` 正文；判断成功须检查正文和非空图片数据。
  Hermes 保留上游错误原因，不自动换模型重试。
- Hermes 返回的 `quality` / `size` 是请求值，不是输出图片的实测元数据。
  2026-09-09 请求 `medium`、`1024x1024`，文生图和编辑实测均为 `1312x1199`；
  2026-10-15 两个 2.5 入口的文生图实测均为可解码的 `1254x1254` PNG。
  不能承诺旁路严格遵守尺寸/质量参数，也不能凭 `low` 档推断实际费用。

2026-10-15 已按先提交推送、再部署的顺序发布功能提交 `facb05d`：
124 图片旁路健康检查正常，Flare 与 Sunburst 均实际生图成功，质量请求保持 `medium`；
81 默认主模型为 `kimi-for-coding`，QQ 已连接，会话、凭据及其他配置保持。
流量日报固定命令实际读取到 12 个公开节点，其中 11 个有完整采样；
本轮未主动发送 QQ 测试消息，不将接口和回归结果宣称为 QQ 人工触发端到端验收。

2026-10-15 核对 124 的 usage 实现，展示模型为 `gpt-6-luna`、`gpt-6-sol`、
`gpt-6.1-sol`、`gpt-6-astra`、`gpt-image-2`、
`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst`，两个 2.5 分别记账。
仅出现展示行不证明模型可用；旁路编排模型仍为 `gpt-5.6-luna`，不能混同。
按 Key 展示不等于多租户隔离；价格是人工维护快照，不保证自动抓取最新价格。

图片费用仅按 Responses 总 `usage` 估算，缺少完整图片模态与编排模型拆账。
编辑路径使用 `gpt-image-2-edit`、`gpt-image-2.5-flare-edit`、
`gpt-image-2.5-sunburst-edit` 作为估算键，它们不是真实
模型。失败按旁路实际状态记账，不因保活 HTTP 200 改记成功；无 token 的失败
不虚构费用，但零估算不代表没有消耗上游额度。

从 NetCup 迁至 124 的入口保留 SDK multipart 编辑请求的模型提取：按 `Content-Type` 解析
`model` 表单字段，不把图片或上传文件内容当作模型名。另保留响应截取上限
2 MiB，在大图 JSON 被截断时用标准 JSON 解码器读取前部完整的顶层 `usage`；
旁路输出顺序为 `created`、`usage`、`data`。缺失或不完整用量仍不补造 token，
不能保证任意第三方响应布局都可恢复用量。历史空模型/零估算记录保持原样。
2026-10-15 核实，正式实现和回归测试位于 124 的
`/root/cliproxyapi-edge-proxy/cliproxyapi_edge_proxy.py` 和同目录
`test_usage_image25.py`；既有 11 项验收结果是 2026-09-09 快照，本轮没有重跑
edge 测试或重算运行时账目。这两个服务器文件不属于 Hermes 本地/GitHub/81 的三端 Git 基线。

以下图片与 QQ 补验结果保留为 2026-09-09 历史记录，不是本次 2.5 兼容发布的新增外发：

当时 81 真实 `_handle_image_generate` 文生图和编辑各一张成功，分别约 36/47 秒，
PNG 完整性和 `MEDIA:<path>` 校验通过，结果存入顶层 `image_cache/`；
两张测试图片已清除。该轮尚未向 QQ 实际投递，不能把工具产图成功当作 QQ 送达验收；
后续 QQ 补验结果见下。
维护验证应走该注册处理器，不能误调仅供 FAL 后端使用的 `image_generate_tool`。
入口修复后又验证了两次合成图片编辑，模型归属均为 `gpt-image-2`；其中一次
SDK 的 2474 tokens 与数据库一致并产生非零估算费用，另一次记录用量为零，
不据此认定实际无额度消耗。全部四张产图及临时输入已清理。Hermes 本轮本地
生图/辅助模型测试 169 项、QQ/媒体标签/skill 同步测试 239 项通过。

2026-09-09 后续补验已通过：网关单次脚本任务调用真实 `_handle_image_generate`，
使用默认 `gpt-image-2` 生成一张 `1254x1254` PNG，经 `MEDIA:` 提取和运行中的
QQ adapter 原生上传发送到唯一允许的阿颜账号。日志确认 live adapter 投递成功，
未记录媒体发送错误；这是服务器投递验收，不代替用户客户端的人工查收。
单次任务、测试脚本、图片、结果文件及任务输出均已清除，没有留下周期任务。
这次补验不涉及聊天模型自主选择工具，也未切换生图模型或修改运行凭据。

## Runtime Data Boundary

Never overwrite or commit server runtime data:

- `/home/hermes/.hermes/.env`
- `/home/hermes/.hermes/config.yaml`
- `/home/hermes/.hermes/memories/`
- `/home/hermes/.hermes/emojis/`
- `/home/hermes/.hermes/sessions/`
- `/home/hermes/.hermes/audio_cache/`
- `/home/hermes/.hermes/image_cache/`
- `/home/hermes/.hermes/cache/`
- `/home/hermes/.hermes/state.db`
- `/home/hermes/.hermes/pairing/`
- `/home/hermes/.hermes/auth.json`
- `/home/hermes/.hermes/mail_vps.toml`

The repo is deployed from `main`. Runtime state is server-local.

## 邮件 helper 的部署形态

- 脚本本体在仓库里：`skills_builtin/mail-vps-ops/bin/mail_vps_fetch.py`，随 git 部署更新。
- `~/.hermes/bin/mail_vps_fetch.py` 是指向 checkout 中该脚本的软链接，所以 skill 和
  文档里的调用路径保持不变。
- 连接参数（主机、端口、SSH 用户、私钥路径）和缓存保留期在服务器本地的
  `~/.hermes/mail_vps.toml`，权限 600，不入仓库；格式见仓库中的
  `skills_builtin/mail-vps-ops/mail_vps.example.toml`。
- 仓库是公开的，脚本里不含任何真实主机、IP 或 SSH 用户名；配置缺失时 helper 返回
  `config_error`，不回退到内置地址。
- 读命令在网络类失败时重试一次（间隔 2 秒），触发条件仅限 ssh 超时和连接失败且远端
  无输出；远端一旦返回 JSON 就视为已执行，不再重试。写命令永不重试，避免超时误判
  导致重复发信或重复删除。81 直连邮件 VPS，不经代理，实测连续 5 次均成功、单次
  2.5–4.5 秒，重试是兜底而非常态。

## 运行账号与权限现状

- 网关以 `hermes` 用户运行（`uid=1001`），附加组 `blogsync`（`gid=1002`）。
- 博客同步依赖 `blogsync` 组：`/www/wwwroot/blog` 为 `drwxrwsr-x root:blogsync`（带
  setgid），同步脚本 `/usr/local/bin/blog-sync-kbase.sh` 为 `-rwxr-x--- root:blogsync`，
  代理私钥 `/etc/blog-sync/proxy.key` 为 `hermes:blogsync`，日志 `/var/log/blog-sync.log*`
  同属该组。定时同步由 **root 的 crontab** 每天 04:00 触发。
- sudo 配置有两份：`/etc/sudoers.d/hermes-gateway-control` 授权 `hermes` 以 root 执行
  `hermes-gateway-control` 的 `status`、`restart`、`logs`；`/etc/sudoers.d/hermes` 为
  `hermes ALL=(ALL) NOPASSWD: ALL`。

## 服务自启与重启策略

81 上与本项目相关的三个 systemd 服务，均为开机自启：

| 服务 | 开机自启 | 异常退出 | 间隔 |
| --- | --- | --- | --- |
| `hermes-gateway.service` | enabled | `Restart=always` | 5 秒 |
| `frps.service` | enabled | `Restart=always` | 5 秒 |
| `nginx.service` | enabled | `Restart=on-failure` | 5 秒 |

- Nginx 的自动拉起是 2026-09-15 通过 `/etc/systemd/system/nginx.service.d/restart-on-failure.conf`
  追加的 drop-in，不是发行版默认；除 `Restart=on-failure` 与 `RestartSec=5s` 外还设了
  `StartLimitIntervalSec=60s`、`StartLimitBurst=5`，即 60 秒内最多重启 5 次。它只在异常
  退出时拉起，正常 stop 不会被重启。
- 博客是 Nginx 提供的静态站点，没有单独的博客进程需要守护。
- FRP 服务端自启与本机侧的 FRP 客户端无关，那是另一端的配置。

## Standard Checks

Use these before and after deployment:

```bash
cd /home/hermes/.hermes/hermes-agent
git rev-parse --short HEAD
git rev-parse --short main
git status --short
git sparse-checkout list
systemctl is-active hermes-gateway.service
systemctl show hermes-gateway.service -p ExecStart --value
HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes \
  /home/hermes/.hermes/venvs/hermes-agent/bin/python -m hermes_cli.main plugins list --plain
git ls-files 'plugins/model-providers/*/plugin.yaml' | cut -d/ -f3 | sort -u
git ls-files 'plugins/image_gen/*/plugin.yaml' | cut -d/ -f3 | sort -u
HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes \
  /home/hermes/.hermes/venvs/hermes-agent/bin/python -m hermes_cli.main skills list --enabled-only
find /home/hermes/.hermes/skills -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
test -f /home/hermes/.hermes/.no-bundled-skills
find /home/hermes/.hermes -path '*/humanizer' -o -path '*/creative'
grep -E 'You are Hermes Agent|created by Nous Research' /home/hermes/.hermes/SOUL.md || true
```

Expected service state is `active`. Expected `ExecStart` uses the external venv
path, not a repo-local `venv`. The runtime skill list should be exactly the six
retained names, the `.no-bundled-skills` guard should exist, and the
`humanizer`/`creative` search should print nothing. The SOUL grep should print
nothing.

## Session Cleanup Timer

The 81 server keeps a systemd timer for old session transcript cleanup:

- Timer: `hermes-session-cleanup.timer`
- Service: `hermes-session-cleanup.service`
- Script: `/usr/local/sbin/hermes-session-cleanup`
- Schedule: `OnBootSec=15m` and `OnUnitInactiveSec=10d`
- 随机延迟：`RandomizedDelaySec=10m`，不是每日任务。
- Policy: `/usr/local/sbin/hermes-session-cleanup --days 10 --delete`
- Scope: deletes old non-active files under `/home/hermes/.hermes/sessions`
- Protection: session IDs still referenced by
  `/home/hermes/.hermes/sessions/sessions.json` are not deleted.
- 仅删除旧 transcript 文件，不清理 `state.db`；产生的
  `session_retention_*/deleted-over-retention.txt` 是删除清单，不是内容备份。
- Unit documentation: this file,
  `/home/hermes/.hermes/hermes-agent/docs/tangyuge-hermes/07-server-operations.md`

2026-10-15 按阿颜本轮明确授权另做了一次全量旧会话清理，这不是定时器策略变更：
网关空闲时停机，以 `sessions/sessions.json` 的唯一映射保留当前会话，
通过 `SessionDB.delete_sessions()` 删除其余两条记录，数据库由 3 条会话、25 条消息
变为 1 条会话、0 条消息。保留的当前会话在操作前本来就是空会话，
其记录、消息及基础提示快照的聚合哈希未变，映射文件逐字节未变；
没有执行 `/new`、`/reset` 或发送测试消息。
清理后完成 FTS 索引、外键及 SQLite 完整性检查，并回收 WAL/空闲数据库页。

Check status:

```bash
systemctl is-enabled hermes-session-cleanup.timer
systemctl is-active hermes-session-cleanup.timer
systemctl list-timers hermes-session-cleanup.timer --no-pager
systemctl cat hermes-session-cleanup.service
```

## 自动任务与季度备份清理

2026-09-15 核验及部署；以下时间均为北京时间。此变更只安装独立运维脚本和
systemd unit，不重启网关、不改变聊天、角色卡、记忆或已有会话。

| 任务 | 调度 | 范围与保留策略 |
| --- | --- | --- |
| `hermes-backup-cleanup.timer` | 每年 1、4、7、10 月 1 日 03:30 | 仅清理 `/home/hermes/backups` 下超过 90 天的已识别旧备份或清单，保护最新一组手工备份 |
| `hermes-session-cleanup.timer` | 见上节，约每 10 天 | 旧非活跃 transcript；不备份内容、不动活跃会话 |
| `/etc/cron.weekly/hermes-cache-cleanup` | 每周日 06:47 | 白名单五项：`logs` 30 天、`audio_cache` 7 天、`image_cache` 14 天、`cache/videos` 7 天、`cache/documents` 14 天；不清理 backups |
| root crontab 的 `/usr/local/bin/blog-sync-kbase.sh` | 每天 04:00 | 同步文章，失败时使用临时回滚副本；退出时清理临时目录，不保留长期备份 |

Hermes 内部 `cron/jobs.json` 在本次核验时任务数为 0。以上不是整机或 Hermes
完整运行数据备份；系统软件包数据库的每日 7 份轮换策略保持不变，云平台快照未核验。

季度清理的本地维护源为 `scripts/ops/hermes_backup_cleanup.py` 及同目录的
`hermes-backup-cleanup.service`、`hermes-backup-cleanup.timer`。服务器安装位置：

- `/usr/local/sbin/hermes-backup-cleanup`
- `/etc/systemd/system/hermes-backup-cleanup.service`
- `/etc/systemd/system/hermes-backup-cleanup.timer`

只接受 `session_manual_cleanup_YYYYMMDD_HHMMSS` 与
`session_retention_YYYYMMDD_HHMMSS` 目录；按目录名称时间、目录及文件修改时间的
最新值计算 90 天门槛，恰好 90 天不删除。手工备份须含非空普通文件
`state.db.backup`，保护其中名称时间最新的一组，即使超过 90 天也保留。
不识别的目录、额外文件、嵌套目录、符号链接及硬链接文件均不进入删除集合。
`Persistent=true` 会在错过季度执行时于后续启动补执行。

```bash
# 只读预演，不删除文件。
python3 -B /usr/local/sbin/hermes-backup-cleanup
systemctl list-timers hermes-backup-cleanup.timer --no-pager
journalctl -u hermes-backup-cleanup.service --no-pager -n 20
```

只有 service 的 `--delete` 模式才执行删除；service 使用 `flock` 防止重叠运行。
2026-09-15 已通过 7 项临时目录测试、unit 校验和 systemd 隔离环境预演，
没有提前执行生产删除。首次计划执行为 2026-10-01 03:30，预演保护
`session_manual_cleanup_20260909_095223`，仅列出 6 月 15 日旧备份为候选。
这是已授权的定期淘汰，不是新增自动备份；被淘汰的历史数据无法靠删除清单恢复。
该任务独立于网关进程；源码和本文随 Hermes 仓库发布，但单独拉取仓库不会自动
更新 `/usr/local/sbin` 与 `/etc/systemd/system` 下的安装副本。后续修改应核对
三份安装文件与 `scripts/ops/` 内容一致，unit 有变化时执行 `systemctl daemon-reload`。
不要为了部署或验收而手动启动带 `--delete` 的 service，也不需要重启网关。

## Deployment Flow

Preferred flow:

```bash
cd /home/hermes/.hermes/hermes-agent
git fetch origin main
git sparse-checkout init --no-cone
git sparse-checkout set --no-cone '/*' '!/tests/' '!/.github/' '!/.plans/' '!/plans/' '!/infographic/' '!/datagen-config-examples/' '!/docker/'
git pull --ff-only origin main
/home/hermes/.hermes/venvs/hermes-agent/bin/python -m pip install -e .
systemctl restart hermes-gateway.service
```

Chat-side restart:

- `/restart` is available to allowed/admin chat users and runs the gateway's
  built-in graceful restart handler.
- In DM only, exact plaintext `restart gateway` is treated as `/restart`.
- This command does not grant arbitrary shell access to the bot.

提示词或角色规则更新后，重启网关仍可能恢复旧会话的基础提示快照。要应用新基础提示
且保留历史，由阿颜执行 `/reset`：下一轮重建提示，同时保留旧会话记录和当前模型、
provider、reasoning 设置。`/new` 会删除旧会话记录并恢复全局默认，不作为本场景的
默认建议。部署不得代为执行会话重置；拼接与缓存契约见 `03-identity-prompt.md`。

`/new`、`/reset` 在忙闲状态共用确认流程；批准前不取消当前任务或清空队列，
取消确认保持原状。未送达或发送中止的文字确认按提示 ID 撤销，不影响后来
替换的确认。原任务已结束时，确认发送异常也会排空期间到达的队列，避免消息滞留。

Chinese operator phrasing:

- If the user says "去维护手册里查重启网关命令", the answer is this section.
- QQ/DM 重启网关命令：`/restart`
- QQ/DM 英文快捷句：`restart gateway`
- SSH 运维重启命令：`systemctl restart hermes-gateway.service`

If GitHub fetch fails from the 81 server, use a local git bundle and fetch it
on the server, then checkout `main`.

## 推理强度设置

- `/reasoning` 查看当前请求等级、作用域和思考显示设置。可选等级为
  `none/minimal/low/medium/high/xhigh/max`，`none` 表示关闭思考。
- QQ 中 `/reasoning max` 仅覆盖当前会话，下条消息生效，不写全局配置；
  `/reasoning max --global` 才保存到 `config.yaml` 的 `agent.reasoning_effort`。
- `/reasoning reset` 清除当前会话覆盖并重新使用全局配置；
  `show/hide/on/off` 仍控制思考内容显示，不是强度等级。
- CLI 的 `/reasoning max` 沿用直接保存全局配置的行为，与 QQ 默认作用域不同。
- 当前 MiniMax-M3 没有因新增枚举获得原生 `max` 能力。其现有手动预算路径将
  `max` 与 `xhigh` 都映射到 32000 token；支持原生 `max` 的 Anthropic 自适应
  路径使用 `output_config.effort=max`。具体效果以目标模型与接口能力为准，
  不要把命令接受枚举理解成所有模型都支持同名等级。
- Kimi Code 只有 `low/high/max` 三档。网关把 `minimal|low` 归到 `low`、
  `medium|high` 归到 `high`、`xhigh|max` 归到 `max`。旧模型 `none` 或显式关闭思考时
  发 `thinking.disabled` 且不带 `reasoning_effort`；K3.1 Pro 系列则明确拒绝关闭思考。
  当前全局是 `low`，思考仍开启，窗口保持 262144。
- 切换模型前先核对接口支持的等级；实现与兼容映射见 `05-patches-and-rtk.md`。

## 模型与上下文命令的作用域

- `/model <name>` 只对当前 QQ 会话生效；`/model <name> --global` 才把
  `model.default`、`model.provider` 写进 `config.yaml`。
- 切换 Kimi Code 的完整写法是
  `/model k3.1-pro --provider kimi-code`，provider 直接写
  `kimi-code`，**不要**加 `custom:` 前缀。
- 上下文窗口跟随同一作用域：会话级 `/model` 保存会话覆盖，
  缓存驱逐后的新 agent、压缩预算与 `/context` 查询使用同一窗口；
  `--global` 才将 `model.context_length` 落盘。回显同时标明来源和作用域，
  CLI 采用同一作用域规则。
- 切换优先采用目标模型的 per-model 配置，再解析模型窗口。
  Kimi 以精确模型 ID 查询官方 `/models`，查询请求带真实客户端标识；
  服务不可达时可用该模型已缓存的窗口；官方与缓存均不可用时，不借用 picker
  中来源不同的 `model_info`，也不会把另一个模型的元数据当作目标模型上限。
- `/model` 无法解析新窗口时，保留切换前该作用域的显式窗口配置，标为
  `retained`；无保留值时采用 `256000`，标为 `fallback`。
  `model_config` 表示目标模型专属配置，`detected` 表示已解析的模型元数据或缓存，
  不用数值是否恰好等于 `256000` 推断来源。
- 保留值包括切换前生效的全局、会话或当前模型专属显式窗口。已识别 Ollama
  且取得自动 `num_ctx` 时，该参数随窗口调整；单独显式设置的 `model.ollama_num_ctx` 保留优先级，
  需要调整它时应修改该配置，不能仅按 `/context` 回显推断请求分配。
  无法识别的本地端点不盲目注入 Ollama 参数；该探测失败边界未作实机验收。
- 需要单独调窗口用 `/context <tokens|256k|1m|auto> [--global]`。单位是
  二进制：`k = 1024`、`m = 1024²`，所以 `512k` 是 524288；不带单位的整数
  按原值处理，`512000` 仍是 512000。显式 `/context auto` 探测失败且无模型
  专属窗口时回落到 `256000`（`250K`），并明确显示 `fallback`。
- `/new`、`/reset` 的窗口回显也使用二进制 K/M，并附精确 token 数；
  `262144` 显示为 `256K (262,144 tokens; ...)`。无法整除单位的数值直接
  显示精确 token 数。`/reset` 回显保留的会话覆盖，`/new` 回显全局配置。
- `/context auto` 绕过全局 `model.context_length`，但仍遵守
  `providers.kimi-code.models.k3.1-pro.context_length` 的 262144。
- 会自动改写 `config.yaml` 的路径只有 `/model` 与 `/context` 的持久化分支，两者现在都只在 `--global` 时落盘。`model_catalog`（默认开启，每 24 小时拉一次上游清单）只写磁盘缓存
  `~/.hermes/cache/model_catalog.json`，不会改动 `config.yaml`，因此不会影响主模型、13 个 `auxiliary` 槽位、`image_gen`、`tts`、`stt`、`x_search` 或 `grok-search` 的既有配置。
- QQ 的 `/model` 不带参数时列表是**空的**，这是有意保留的行为：
  `gateway/run.py` 的 `_filter_dialog_model_providers()` 把可列出的
  provider 限定在 `openrouter`、`deepseek-direct`，旧小米入口已移除，
  而这两个在 81 runtime 上都不使用，因此过滤后为 0 条。切换模型一律用上面
  的显式命令。副作用：上游用例
  `tests/gateway/test_model_command_custom_providers.py::test_handle_model_command_lists_saved_custom_provider`
  断言列表会展示自定义 provider，在本项目中长期失败，属于该取舍的已知结果，
  不是回归，也不要为了让它通过而放开白名单。

## Kimi Code 请求与缓存

原始核验日期：2026-09-16；新版复核日期：2026-10-23，缓存与配置收尾复核至 2026-10-24。实际端点为
`https://api.kimi.com/coding/v1`，采用原生 OpenAI Chat Completions 协议。
下方旧模型请求参数保留为原日期快照；当前配置以前面的运行形态及本节新版验证为准。

### 身份与会话

- 请求以 `Tangyuge-Hermes/<hermes_cli.__version__>` 标识客户端。客户端身份
  描述调用软件，角色卡描述对话人格，两者承担不同职责。
- 主对话以实际 `session_id` 派生 `prompt_cache_key`，同一会话恢复后保持
  稳定；会话轮换时更换。派生键使用 SHA-256，内容不包含明文用户资料。
- 独立辅助操作使用任务级缓存键；其身份标识与主对话一致。共享客户端和连接池
  不代表共享业务会话。重试属于同一任务，应沿用其键。
- OpenCode Go 文档的 `x-opencode-session` 属于该服务的接入协议。
  本项目直连 Kimi，依据 Kimi 的 `prompt_cache_key` 契约发送请求。

### 请求体与验证边界

- 2026-09-16 快照：主模型使用 `k3-256k`、`reasoning_effort: low` 与
  `thinking.type: enabled`；全局窗口为 262144，模型专属配置按前面的运行形态维护。
  辅助任务的参数按自身调用链解析，不能从主模型配置推断其实际发出的思考参数。
- assistant 历史中的 `reasoning_content` 与工具调用消息按现有回传链路保留。
  角色、SOUL、MEMORY、USER 的基础提示是会话快照；工具 schema 独立发送，
  动态平台上下文按请求追加。稳定缓存键是路由线索，前缀内容变化仍会影响命中。
- 用量兼容 `usage.prompt_tokens_details.cached_tokens` 和顶层
  `usage.cached_tokens`，两者同时存在时不重复计数。响应缺少缓存统计时只能
  说明服务没有报告，不能宣称已经命中，也不能根据订阅费用展示反推命中率。
- 真实连通验收使用最小编程请求和独立任务键，不发送用户聊天历史。
  HTTP 200 证明该次请求被接受；缓存命中、QQ 投递和人物表现分别验收。
- Kimi Code 订阅面向编程场景。其他用途的许可应以账号条款及官方确认为准；
  协议适配与真实客户端标识不构成账户风控或订阅使用范围的保证。

### K3.1 Pro 新版验证

- 官方订阅模型 ID 是 `k3.1-pro`；开放平台的 `kimi-k3.1-pro` 不是本部署使用的 ID。
  官方依据：<https://www.kimi.com/code/docs/kimi-code/models.html> 与
  <https://www.kimi.com/code/docs/third-party-tools/hermes.html>。
- 使用现有订阅 Key 直连 `/coding/v1/chat/completions`，沿用
  `Authorization: Bearer ...`、JSON 请求体、真实 `Tangyuge-Hermes/<版本>` 标识及
  哈希任务缓存键。初次验收的实际主对话请求为 `model=k3.1-pro`、`thinking.type=enabled`、
  `reasoning_effort=high`，返回同名模型；随后按本人最新要求将全局档位改为 `low`，
  窗口仍为 262144。不伪装其他软件或增加未经要求的签名。
- 真实合成图片正确识别绿色圆形与蓝色方形；四秒合成 MP4 经 `video_url` base64
  直接上传，正确识别红色到蓝色的时序，不是预先抽帧生成文字摘要。
  `tool_choice=auto` 的工具调用与带 reasoning 历史的续轮均返回 200。
- 部署后另以临时 home、隔离 SessionDB 和禁用工具的真实 `AIAgent` 主对话验证：
  同一请求携带合成图片与视频，正确回答图形和视频时序；续聊仍正确。
  实际流式发包只有一个 system 消息，保留 `image_url` / `video_url` 和续轮 reasoning。
  测试没有读取运行记忆或聊天历史，临时 home 已移除；这不是实际 QQ 会话验收。
- 强制指定函数的协议探针返回 400，提示与思考模式不兼容；正常主对话不使用该探针。
  不能通过关闭 K3.1 思考来规避，也不能把此探针报错当作正常 QQ 生产错误。
- 补查真实辅助 `call_llm` 时发现新裸 ID 未命中 Kimi 温度规则，调用方的 `0.2`
  被上游以“仅支持温度 1”返回 400。这是真实辅助兼容缺口，现已将两个新 ID 纳入
  原有温度省略规则；主对话与辅助调用均由上游使用合法默认温度，不改全局配置。
  部署修复后以同一真实辅助调用复测成功，现场无温度覆写配置。该辅助请求未显式发送
  `thinking` / `reasoning_effort`，由上游使用模型默认思考，不能说成辅助也显式跟随主对话档位。
  不能把这条实际缺陷与前面的强制工具负向探针混为一谈。
- 响应签名是另一项真实性校验能力，不是 Bearer 鉴权的替代。本轮通过
  `X-Msh-Request-Nonce` 携带随机 nonce，
  coding 端点没有返回 `Msh-Request-Signature` / `Msh-Request-Timestamp`，因此未完成
  密码学验签，不将响应的 `model` 字段说成签名证明。
- 默认模型变更不等于历史会话迁移。官方建议换代后新建会话，避免混用旧模型思考历史；
  本轮不删除或自动重置会话。`/new` 由本人决定执行，不能默默清空聊天记录。
- 本轮未发送真实 QQ 测试消息，也未逐一测试高速版、超长上下文或大型视频；
  45 MiB 内联预算与原有文件上传分类保持不变，超预算仍回落文本路径。
- 辅助温度补丁后的最终正式精简测试集为 1694 项通过、14 项跳过；补丁定向回归
  为 96 项通过，Ruff 通过。额外调用保留范围以外的上游
  provider 测试曾出现 28 项失败；在独立测试进程中将本轮修改模块换回原 HEAD 源码后，
  同一批 28 项仍失败，不能说成新增回归，也不宣称整个上游测试库全绿。

### 缓存时长与额度窗口

- 2026-10-24 只读复核实际 K3.1 会话的累计 `cache_read_tokens` 非零，已有缓存命中；
  不需要再发送合成重复请求来证明同一事实。数据库的 `input_tokens` 是归一化后的
  未缓存输入，不能直接用缓存读取量除以它计算命中率。
- 通用 Kimi API 官方文档支持
  `prompt_cache_options: {"mode": "implicit", "ttl": "5m" | "1h"}`；这是开放平台
  Chat Completions / Responses 的显式写入设置，不等于 Coding Plan 订阅端点的承诺。
  当前查阅的 Code 模型、会员、FAQ 与更新文档没有明确公开同一参数的订阅支持保证；
  不声称订阅一定支持或一定不支持，不盲目向订阅请求添加 TTL。
- 本项目现有 `prompt_caching.cache_ttl: 5m` 只属于 Anthropic 路径，
  `prompt_cache_key` 只提供会话路由线索，两者都不能代替订阅服务端的 TTL 设置。
  保持模型、思考档位与稳定前缀一致有助复用；改模型、改思考、压缩或改写前缀可能降低命中。
- 5 小时频率窗口、缓存保留时间、上下文压缩阈值是三个不同概念。计费倍率及官方额度
  重置由上游处理，不靠修改模型请求头、伪装客户端或自行传入折扣比例实现。
  本轮未独立取得后台重置和特定倍率调整的账号级证据，不把用户告知的调整包装成验签结论。
- TTL 的官方作用域依据：
  <https://www.kimi.com/academy/best-practices-for-context-caching>；
  订阅额度窗口依据：<https://www.kimi.com/code/docs/kimi-code/membership.html>。

### 维护资料

- Kimi API 字段：<https://platform.kimi.com/docs/api/chat>。
- Kimi Code 接入与身份要求：<https://www.kimi.com/code/docs/>。
- 官方 CLI 请求构造：<https://github.com/MoonshotAI/kimi-cli/blob/main/src/kimi_cli/llm.py>。
- 官方请求适配器：<https://github.com/MoonshotAI/kimi-cli/blob/main/packages/kosong/src/kosong/chat_provider/kimi.py>。
- OpenCode Go 协议：<https://opencode.ai/docs/go/>。
- 实现与回归入口：`agent/kimi_code.py`、CustomProfile、辅助客户端、
  `tests/agent/transports/test_kimi_code_custom_profile.py`、
  `tests/agent/test_kimi_cache_usage.py`。

## 运行记忆维护

`memories/MEMORY.md` 保存本机路径和工具流程，`memories/USER.md` 保存称呼、
沟通和时间偏好，`SOUL.md` 补充工作风格；角色卡负责身份、关系和人格。
工具能力与可接受参数以当前 schema 和实际配置为准。

路径速查使用本页四类媒体缓存表。`text_to_speech` 的提供方由运行配置确定，
工作站场景与参考音频的选择见下一节。日常时间默认采用北京时间，
用户指定其他时区时按要求换算并标明。

这些文件在基础提示构建时读取。维护文件不直接覆盖活动会话的冻结提示；
需要立即采用最新记忆时，由阿颜执行 `/reset`，保留旧记录并建立新会话。
部署和核验不代为执行会话删除或重置。

## 工作站 TTS 参数

TTS 运行在另一台 Windows 工作站，部署目录为
`C:\service\tangyuge_tts_workstation_bundle`，由 `TangyugeTTS` 服务管理。
服务器 `127.0.0.1:19880` 经 SSH 反向隧道连接工作站 bridge `9881`，
bridge 再调用 GPT-SoVITS `9880`。工作站离线时合成不可用，Hermes 其他能力独立运行。
本地训练与协议源码位于 `D:\MCP_Server\galgame-skills\Tangyuge-TTS-assets`。

`text_to_speech` 接受 `text`、可选 `output_path`，在
`remote_gptsovits` 命令提供方下另接受：

- `scene`：场景别名，例如 `soft`、`morning`、`romantic`、`question`、
  `narration`、`intimate`；工具 schema 列出可用别名。
- `profile`：工作站已有配置名称，例如 `soft_daily`、`morning`、
  `romantic_soft`、`main_hybrid_mid`。
- `reference`：工作站参考音频清单中的 `id`，不是文件路径。

选择优先级为 `reference > profile > scene > 文本自动选择`。
完整配置和参考清单可在工作站在线时，经服务器访问
`http://127.0.0.1:19880/profiles` 与 `/references` 读取；不要猜测参考 ID。
模型可按语境自主选择已有风格；未指定参数时保留自动选择。
其他提供方接到这些选择参数会明确报错，避免无声忽略。

命令提供方为参数生成临时 JSON，通过 `{metadata_path}` 传递。
实际入口为仓库 `scripts/tts_remote_gptsovits_bridge.py`；
runtime `/home/hermes/.hermes/tts_remote_gptsovits_bridge.py` 是其软链接。
运行配置：

```yaml
tts:
  provider: remote_gptsovits
  providers:
    remote_gptsovits:
      type: command
      command: python3 /home/hermes/.hermes/tts_remote_gptsovits_bridge.py {input_path} {output_path} {metadata_path}
      timeout: 300
      max_text_length: 2000
      voice_compatible: true
      format: wav
```

转发入口固定向本机隧道发送一次 `/tts` 请求，指定非流式 WAV，
校验音频容器后写入文件；由 Hermes 既有音频转换流程生成语音格式。
临时文本和 metadata 在成功或失败后清理；合成超时不自动重发。
`tests/tools/test_tts_remote_metadata.py` 离线覆盖参数到 HTTP 请求的完整链路，
不代表工作站真实合成或 QQ 实际投递已通过。

## Documentation Rule

For bot-readable documentation, update repo docs under
`docs/tangyuge-hermes/` and redeploy. KBase records on the Windows machine are
operator notes only, not installed into the Hermes runtime or used by the locator.

KBase 只有阿颜明确授权后才能更新；默认改动只留本地，不提交、不推送、不运行博客同步。
只有当次另行明确授权时才执行相应发布动作。博客同步可把公开记录发布为文章，
不等于将 KBase 安装成 Hermes 开发文档或运行时定位源。
NowledgeMem/nmem 与 Serena 指维护侧记忆，不是 Hermes runtime 的 `memories/`；
读取或核对记忆不等于获准写入，也不改变 Hermes 自身记忆工具的既有行为。
维护侧记忆的写入、合并、替换和删除均须阿颜明确授权，只保留长期稳定规则、
当前主状态和关键部署事实，不写临时日志、验证流水账或密钥内容。

## Cleanup Rule

After deployment or documentation changes:

- 三端基线只指本地 Git HEAD、GitHub `main` 和服务器 checkout HEAD；
  WSL 是本地工作区的访问视图，KBase 和服务器 runtime 数据不计入三端基线。
- Remove local and server `.bundle` deployment archives after successful use.
- `.doc-maintenance/` 是本地临时审阅目录，保持 Git 忽略并在完成后删除；
  不推送、不部署，不在 KBase 内生成。不要用 `git clean -fdX` 一刀切清理。
- Keep server runtime data under `/home/hermes/.hermes/` intact; never replace
  `.env`, `config.yaml`, memories, sessions, media caches, or user documents.
- Keep `/home/hermes/.hermes/skills` aligned to the six retained skills and
  keep `/home/hermes/.hermes/.no-bundled-skills` in place. Preserve
  server-local secret files such as skill `.env` files when resyncing skill
  directories.
- Keep `/home/hermes/.hermes/SOUL.md` as a clean style overlay when prompt or
  identity code changes; do not restore old upstream default identity text.
- 旧 home 文档、代码备份和 `.bak` 删除前，先核查引用、运行依赖及恢复价值，
  明确精确路径后再清理，不按文件后缀或年龄批量删除。
- 清理会话前的 SQLite 快照可能保存当前库已删除的历史数据；不能仅因文件旧、
  没有运行引用或现用数据库正常而判定冗余。无法证明没有恢复价值时保留。
- 例外是 2026-09-15 阿颜明确授权的“自动任务与季度备份清理”范围；
  不得将其 90 天规则扩展到其他路径、备份类型或 runtime 数据。
- SSH 备份（例如 `known_hosts.old`）只有在确证内容冗余、没有独立恢复价值后
  才可清理；不得连带删除或改写现用 SSH 文件。
- 获得记忆更新授权后，优先维护既有 Tangyuge-Hermes 当前状态主条目；
  不把过时快照当作当前状态，也不创建重复的平行条目。
