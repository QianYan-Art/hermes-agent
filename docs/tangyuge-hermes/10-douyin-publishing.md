# 抖音作品与草稿

常用叫法：抖音发布、保存抖音草稿、序栞、OpenFilm 成品、作品包、抖音后台数据、
`douyin_content`。登录与人工验证窗口另见 `09-douyin-login.md`。

## 作品来源

OpenFilm 规范以本机项目的 `START.md`、`docs/目录规范.md`、`docs/工作记录.md`
及 `qianyan-film-pipeline` 为准。序栞工程是 `Projects/my-ip`，之后每期是与其
并列的 `Projects/yu-epNN-<主题>`。成品保留在各项目根目录，序栞为
`ep00-序栞.mp4`；不要把整个工程、素材、声音模型、共享 skills 或 `.film/`
复制到服务器，也不要在发布时重新渲染。Studio 导出的字幕已烧录，命令行导出
不能据此冒称带字幕。制作与发布是两个流程，不改变唐语歌人格或全局提示词。

## 暂存格式

服务器的有效运行数据为：

```text
/var/lib/hermes-douyin/releases/<release_id>/
  manifest.json
  video.mp4
```

作品包只允许这两个普通文件，拒绝符号链接与路径穿越。视频上限 512 MiB。
清单声明版本、作品编号、标题、简介、AI 生成标记、视频 SHA-256、大小、时长、
宽高、帧率和 UTC 创建时间。`release_id` 仅允许小写 ASCII 字母、数字与连字符，
最多 64 字符；标题为 1 到 30 字符，简介最多 1000 字符；`ai_generated` 必须为
true。可选 `source` 仅作来源说明，不包含密钥。服务器安装和实际操作都校验
视频摘要；同编号相同内容可重复安装，不同内容不能覆盖，修订成片应换编号。

本机使用 `ops/douyin-login/stage_release.py prepare` 读取已导出的 MP4，调用
`ffprobe` 核对 H.264/AAC 和媒体参数，只生成清单，不改变或复制原片：

```powershell
python ops/douyin-login/stage_release.py prepare --video "<成品.mp4>" --release-id ep00 --title "<标题>" --description "<简介>" --source "OpenFilm Studio，字幕已烧录" --output "<临时清单目录>/manifest.json"
```

运维通过已有 SSH 加密连接，将该清单与选定的原片传到 root 私有临时目录，
远端文件名分别为 `manifest.json` 和 `video.mp4`，再以 root 执行：

```bash
python ops/douyin-login/stage_release.py install --source-dir <私有临时作品包目录>
```

安装使用 `--data-dir` 指定数据根目录时，也不能覆盖 profile 或其他运行目录。
默认数据根目录是 `/var/lib/hermes-douyin`，归 `douyin-runner` 与
`hermes-douyin`，目录 0700、文件 0600。安装后删除传输临时副本，保留有效作品。
已暂存的作品可在本机离线时操作；还没同步的新一期不能靠服务器读取 Windows 路径。

## 工具契约

作品入口与原 `douyin_login` 使用同一个受 UID 校验的 Unix socket；模型不会
取得任意浏览器、URL、磁盘路径或 Cookie 接口。`douyin_content` 仍只允许指定
QQ 用户的精确私聊，其他平台与群聊拒绝；CLI 运维不能绕过公开发布确认。

- `list`：列出服务器已暂存的作品摘要。
- `prepare`：给出作品编号及可选标题、简介，核对账号并返回短期 `token` 和物料
  预览，不点击发布。令牌绑定视频摘要、元数据和预期账号，有效 15 分钟。
- `draft`：用准备令牌创建后台保存任务，返回 `job_id`。
- `job`：查询原任务，不用反复重新发起上传；`in_progress` 不等于完成。
- `metrics`：只读取创作者中心首页当前可见字段，返回来源与采集时间；无字段
  不代表数值为零，不宣称取得官方 API 或未开通权限。
- `publish`：必须已有相同物料的成功草稿，且阿颜在同一 QQ 私聊亲自全文发送
  `确认发布 <token>`。插件只从真实入站消息记录 120 秒、单次消费的确认，
  模型自填 `confirmed=true`、模型输出确认文本或旧消息重放均不放行。

准备与数据读取的服务端上限为 40 秒，小于插件的 50 秒通信上限；视频任务
后台执行，最长 10 分钟，不将上传等待塞进一个短时 RPC。

正式发布前还会核对草稿可唯一定位、标题和简介一致、平台 AI 声明确实选中。
声明证据只接受唯一可见的具体复选、单选或选项控件，不凭任意祖先元素包含文字放行。
无法唯一定位、验证受阻或声明未确认时停止，不重新上传后直接发布。简介里写
“AI 生成”不能替代平台声明。保存草稿时若声明尚不能确认，结果明确提示，
公开发布仍强制检查。默认使用平台抽帧封面，不宣称封面已由阿颜确认。

后台任务状态持久化在 `content-jobs/`，物料令牌在 `content-plans/`，均是私有
运行数据。保存或发布结果不明、连接中断、超时或重启后，一律标记
`needs_attention`，相同操作只返回原任务，不自动再次点击。用户先核对平台实际
结果，不能把普通 `page_error` 当作可以重复发布的理由。

## 当前验证边界

本轮阿颜只授权将序栞保存为草稿，不授权正式发布。自动测试验证协议、摘要、
路径、确认来源、防重和恢复，不替代真实草稿保存与 QQ 投递。当前代码仍须部署
并进行真实草稿验收后才能宣称该链路通过；公开发布不在本轮实发测试范围。

新增模块与安装器、插件源码一并提交推送并核实 GitHub 后再部署；只重启需要更新
的独立服务及空闲 QQ 网关，不覆盖 profile、会话、SOUL、USER/MEMORY 或其他服务。
本机和服务器临时包、测试文件与诊断材料在验证后定向清理；有效视频、草稿、
状态账本和登录目录不是残留，不得一并删除。
