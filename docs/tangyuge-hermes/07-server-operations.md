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

Default model provider:

- Provider slug: `kimi-code`（`providers:` 下的命名自定义 provider，运行时
  解析出的内部 provider 名是 `custom`）
- Display name: `kimi-code`
- Base URL: `https://api.kimi.com/coding/v1`
- Default model: `k3-256k`
- Key env: `KIMI_CODE_API_KEY`（值只存 runtime `.env`，不入仓库和文档）
- Transport: 显式 `chat_completions`。必须显式写，否则 URL 自动检测会把
  `/coding` 当成 Anthropic 协议。
- Context length: 全局 `model.context_length` 为 `262144`。
  `k3-256k` 的官方 `/models` 在 2026-09-16 返回 `262144`，即二进制 `256K`。
  `providers.kimi-code.models.kimi-for-coding.context_length` 单独设为
  `262144`，约束的是 `kimi-for-coding`；该模型接口自报 1048576。
  注意窗口只认 per-model 的 `models.<model>.context_length`，
  **不认** provider 顶层的 `context_length`。
- `agent.reasoning_effort` 全局为 `low`。Kimi 的思考参数由
  `plugins/model-providers/custom/` 的 Kimi Code 分支发出：
  `extra_body.thinking.type` 为 `enabled`/`disabled`，并映射
  `minimal|low -> low`、`medium|high -> high`、`xhigh|max -> max`。
  该分支只匹配主机 `api.kimi.com` 且路径为 `/coding` 或 `/coding/v1`，
  其他自定义 provider 与 Ollama 行为不变。
- MiniMax 转为备用：`MINIMAX_CN_API_KEY` 保留在 `.env`，内置 `minimax-cn`
  provider 仍可用，但不再是默认主模型。
- The old main-model custom providers `openrouter`, `siliconflow`,
  `deepseek-direct`, and `xiaomi-token-plan-cn` are not used on the 81 runtime.
  Auxiliary/vision, image generation, and TTS settings are separate and should
  not be removed when cleaning main model providers.
- `DEEPSEEK_API_KEY` may remain in `.env` as a fallback key, but the default
  main model does not use it.
- `prompt_caching.cache_ttl` is `5m`。该缓存语义是 Anthropic 兼容路径
  （`cache_control` 标记 + 5 分钟续期）的行为；Kimi Code 走
  `chat_completions`，不适用这条 Anthropic 缓存路径。
- `agent.image_input_mode` is `auto` and `auxiliary.vision.provider` points to
  `custom:ollama_vision`, so QQ images are summarized by the auxiliary vision
  backend instead of being sent to the main model. 图片链路与主模型无关，
  切换默认模型不影响它。
- QQ videos are routed independently from images. 能否内联上传由
  `agent/image_routing.py` 的 `supports_native_video_input()` 判定，目前有两条
  已验证路径：
  - MiniMax：provider 属于 `{minimax, minimax-cn}` 且模型名以 `minimax-m3`
    开头，视频作为 Anthropic 兼容的原生 `video` block 上传。
  - Kimi Code：端点为 `api.kimi.com` 的 `/coding` 或 `/coding/v1`，且模型是
    `kimi-for-coding`、`kimi-for-coding-highspeed` 或 `k3`，视频作为
    OpenAI 兼容的 `video_url` base64 data URL 上传，与图片同形。
    **`k3-256k` 按官方模型对比表不支持视频**，不在名单内。
  命名自定义 provider 运行时解析成 `custom`，所以 Kimi 这条靠 base_url 识别，
  相似主机名不会误命中。不在名单内的模型回落到缓存路径文本标记。
  内联预算两条路径共用：单文件 45 MiB、单轮合计 45 MiB，超出即回落。
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
  `deepseek`, `minimax`, `minimax-cn`, and `minimax-oauth`.
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

- `delegate_task(background=true)` is available for single-task async
  subagents. Results return to the same session through the gateway completion
  watcher.
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
- QQBot approval buttons are active for dangerous command approvals. `允许一次`
  resolves the current pending approval only, `始终允许` persists the approval
  through the normal permanent allowlist path, and `拒绝` denies it. If a
  clicked button no longer has a pending approval to resolve, the bot replies
  that the authorization request has expired or already been handled.
- `hermes plugins list --plain` should list only `disk-cleanup`,
  `rtk-rewrite`, and `security-guidance`.
- Retained web/browser plugin shims may remain in the repo even though they are
  not standalone plugins, because retained `web` and `browser` toolsets import
  those provider modules directly.
- Non-retained model provider packages and non-OpenAI image provider packages
  are physically removed from the tracked source after retained-scope tests
  prove they are no longer referenced.

## 生图旁路与 Usage

2026-09-09（UTC）核对的 81 配置：`image_gen.provider=openai`，
`image_gen.model` 和 `image_gen.openai.model` 均为 `gpt-image-2-medium`；
实际请求 `api_model=gpt-image-2`、`quality=medium`。
`image_gen.openai.base_url=https://suyuan.4071253.xyz/v1`，
`image_gen.openai.timeout=180`。图片专用密钥在 `OPENAI_IMAGE_API_KEY`，
现场未设置其他图片模型环境覆盖；不将密钥写入仓库或文档。

请求从 EdgeOne 经 NetCup nginx 到 `cliproxyapi-edge-proxy`（回环 59999），
图片转交 `cliproxyapi-image-proxy`（60001），普通模型请求转交 CLIProxyAPI（59998）。
旁路使用 ChatGPT Codex 后端，内部编排模型是 `gpt-5.6-luna`；它不是图片工具
模型，也不是 Hermes 主聊天模型。官方 Images API 的模型支持不等于该账号通道权限。

旁路请求名和执行边界：

- 默认和 `gpt-image-2` 使用 Image-2；`gpt-image2` 是同一模型的兼容别名。
- `gpt-image-2.5-flare`、`gpt-image-2.5-sunburst` 保留同名请求；
  `gpt-image-2.5` 仅是本地映射到 Flare 的便利别名。未知名称返回 HTTP 400。
- 当前账号通道的 2.5 请求终态仍声明 `gpt-image-2-codex`，严格校验会返回
  `image_model_unavailable`，不会把旧模型图片冒充 2.5。默认 Image-2 保持不变，
  不自动切换，也不猜下架时间。
- 文生图和编辑支持 `n=1..10`；`response_format=url` 返回 data URL，不是图床链接。
  `variations` 只有入口路由与鉴权覆盖，图片旁路未实现该功能。
- 入口先鉴权再读取大图片；缺失或错误密钥返回 401。超过 10 秒保活后，
  后续失败可能表现为 HTTP 200 加 `error` 正文；判断成功须检查正文和非空图片数据。
  Hermes 保留上游错误原因，不自动换模型重试。
- Hermes 返回的 `quality` / `size` 是请求值，不是输出图片的实测元数据。
  本轮请求 `medium`、`1024x1024`，实际文生图和编辑均为 `1312x1199`；
  不能承诺旁路严格遵守尺寸/质量参数，也不能凭 `low` 档推断实际费用。

usage 由 NetCup 入口聚合，顶部展示七个家族：`gpt-5.5`、`gpt-5.6-luna`、
`gpt-5.6-sol`、`gpt-5.6-terra`、`gpt-6-astra`、`gpt-image-2`、
`gpt-image-2.5`。两个 2.5 型号归入同一展示家族，出现该行不证明权限可用。
按 Key 展示不等于多租户隔离；价格是人工维护快照，不保证自动抓取最新价格。

图片费用仅按 Responses 总 `usage` 估算，缺少完整图片模态与编排模型拆账。
编辑路径使用 `gpt-image-2-edit` / `gpt-image-2.5-edit` 作为估算键，它们不是真实
模型。失败按旁路实际状态记账，不因保活 HTTP 200 改记成功；无 token 的失败
不虚构费用，但零估算不代表没有消耗上游额度。

NetCup 入口已修复 SDK multipart 编辑请求的模型提取：按 `Content-Type` 解析
`model` 表单字段，不把图片或上传文件内容当作模型名。另保留响应截取上限
2 MiB，在大图 JSON 被截断时用标准 JSON 解码器读取前部完整的顶层 `usage`；
旁路输出顺序为 `created`、`usage`、`data`。缺失或不完整用量仍不补造 token，
不能保证任意第三方响应布局都可恢复用量。历史空模型/零估算记录保持原样。
正式实现和回归测试位于 NetCup 的
`/root/cliproxyapi-edge-proxy/cliproxyapi_edge_proxy.py` 和同目录
`test_usage_image25.py`，11 项测试使用临时数据库，未重算运行时账目。
这两个 NetCup 文件不属于 Hermes 本地/GitHub/81 的三端 Git 基线。

本轮 81 真实 `_handle_image_generate` 文生图和编辑各一张成功，分别约 36/47 秒，
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
  `medium|high` 归到 `high`、`xhigh|max` 归到 `max`；`none` 或显式关闭思考时
  发 `thinking.disabled` 且不带 `reasoning_effort`。当前全局是 `low`。
- 切换模型前先核对接口支持的等级；实现与兼容映射见 `05-patches-and-rtk.md`。

## 模型与上下文命令的作用域

- `/model <name>` 只对当前 QQ 会话生效；`/model <name> --global` 才把
  `model.default`、`model.provider` 写进 `config.yaml`。
- 切换 Kimi Code 的完整写法是
  `/model kimi-for-coding --provider kimi-code`，provider 直接写
  `kimi-code`，**不要**加 `custom:` 前缀。
- 上下文窗口跟随同一作用域：会话级 `/model` 保存会话覆盖，
  缓存驱逐后的新 agent、压缩预算与 `/context` 查询使用同一窗口；
  `--global` 才将 `model.context_length` 落盘。回显同时标明来源和作用域，
  CLI 采用同一作用域规则。
- 切换优先采用目标模型的 per-model 配置，再解析模型窗口。
  Kimi 以精确模型 ID 查询官方 `/models`，查询请求带真实客户端标识；
  服务不可达时可用该模型已缓存的窗口。不会把另一个模型的元数据当作目标模型上限。
- `/model` 无法解析新窗口时，保留切换前该作用域的显式窗口配置，标为
  `retained`；无保留值时采用 `256000`，标为 `fallback`。
  `model_config` 表示目标模型专属配置，`detected` 表示已解析的模型元数据或缓存，
  不用数值是否恰好等于 `256000` 推断来源。
- 需要单独调窗口用 `/context <tokens|256k|1m|auto> [--global]`。单位是
  二进制：`k = 1024`、`m = 1024²`，所以 `512k` 是 524288；不带单位的整数
  按原值处理，`512000` 仍是 512000。显式 `/context auto` 探测失败且无模型
  专属窗口时回落到 `256000`（`250K`），并明确显示 `fallback`。
- `/new`、`/reset` 的窗口回显也使用二进制 K/M，并附精确 token 数；
  `262144` 显示为 `256K (262,144 tokens; ...)`。无法整除单位的数值直接
  显示精确 token 数。`/reset` 回显保留的会话覆盖，`/new` 回显全局配置。
- `/context auto` 绕过全局 `model.context_length`，但仍遵守
  `providers.kimi-code.models.kimi-for-coding.context_length` 的 262144。
- 会自动改写 `config.yaml` 的路径只有 `/model` 与 `/context` 的持久化分支，两者现在都只在 `--global` 时落盘。`model_catalog`（默认开启，每 24 小时拉一次上游清单）只写磁盘缓存
  `~/.hermes/cache/model_catalog.json`，不会改动 `config.yaml`，因此不会影响主模型、13 个 `auxiliary` 槽位、`image_gen`、`tts`、`stt`、`x_search` 或 `grok-search` 的既有配置。
- QQ 的 `/model` 不带参数时列表是**空的**，这是有意保留的行为：
  `gateway/run.py` 的 `_filter_dialog_model_providers()` 把可列出的
  provider 限定在 `openrouter`、`deepseek-direct`、`xiaomi-token-plan-cn`，
  而这三个在 81 runtime 上都不使用，因此过滤后为 0 条。切换模型一律用上面
  的显式命令。副作用：上游用例
  `tests/gateway/test_model_command_custom_providers.py::test_handle_model_command_lists_saved_custom_provider`
  断言列表会展示自定义 provider，在本项目中长期失败，属于该取舍的已知结果，
  不是回归，也不要为了让它通过而放开白名单。

## Kimi Code 请求与缓存

核验日期：2026-09-16。实际端点为 `https://api.kimi.com/coding/v1`，
采用 OpenAI Chat Completions 协议。

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

- 主模型使用 `k3-256k`、`reasoning_effort: low` 与
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
