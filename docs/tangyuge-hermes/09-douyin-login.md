# 抖音服务器登录

浏览器按需运行：首次浏览器请求才启动真实 Chromium，180 秒空闲后正常关闭，
保留独立 profile；轻量 Unix socket 服务仍在，后续请求可重新启动浏览器。
后台上传与关闭共用互斥锁，任务执行期间不回收。当次临时人工窗口最多豁免 15 分钟。
这不是安卓模拟器，也不要求阿颜日常打开 noVNC；窗口仅用于登录验证或异常核查。

常用叫法：抖音登录、抖音扫码、抖音账号状态、服务器抖音、OpenFilm 发布。

## 当前范围

本页说明 `douyin_login` 工具：`action=status` 检查服务器页面，
`action=login` 在需要登录时取得二维码。该工具本身不上传、不发布、不修改账号。
作品暂存、草稿、逐次确认和可见数据读取另见 `10-douyin-publishing.md`；
不能把登录验收通过称作公开发布已实测通过，不自动开通数据中心。

普通个人号没有开放平台应用，本接入使用创作者中心独立浏览器，不宣称取得官方
发布 API 权限。Windows OpenFilm 工程和素材不上传、不整理；独立手动导出不会触发同步。
本系列制作代理会在 Studio 导出验收后自动同步选定成品，详见 `10-douyin-publishing.md`。
电脑离线时不能读取尚未同步的新片；已入库作品可在服务器操作，正式发布仍需逐条确认。

## 使用

- 阿颜在指定 QQ 私聊说“检查抖音登录状态”，调用 `douyin_login(action="status")`。
- 说“登录抖音”时调用 `douyin_login(action="login")`，若返回 `media_tag`，
  必须在本次私聊最终回复中原样带上标签，QQ 才会投递二维码。不要转发至其他会话。
- 阿颜用抖音手机端扫码并确认后，再检查状态；二维码过期则再次请求登录。
  明确检测到二维码过期时，`login` 只刷新固定登录页；等待手机确认时不重复发码，
  已识别正确账号登录时也不重新导航或登录。
- `logged_in` 必须同时识别创作者后台和配置的账号，不以页面可打开或 Cookie 存在为依据。
- `unknown` 不代表退出；`account_mismatch` 不代表可以自行切号；
  `verification_required` 需要人工完成验证，不解验证码、不绕过风控、不反复尝试。
- 不要求阿颜的 Windows 电脑在线，也不读取或迁移 Codex 浏览器的登录数据。

## 隔离与配置

插件源码在 `ops/douyin-plugin/`，按用户插件部署到
`$HERMES_HOME/plugins/douyin-login/`，在 `plugins.enabled` 加入 `douyin-login`，
在 `platform_toolsets.qqbot` 加入 `douyin`。这是独立插件，不加入裁剪后的 bundled
插件白名单、不改变全局 browser/CDP 和 TTS 设置。`hermes tools` 的裁剪界面不会
列出该工具组；以实际模型工具 schema 和注册结果为准。

`DOUYIN_OWNER_QQ_USER_ID` 限制指定用户且 chat_id 与 user_id 相同、会话键为
`agent:main:qqbot:dm:<指定用户>` 的 QQ 私聊；
其他平台、群聊均拒绝。无网关上下文的本机运维入口允许调用，但仍受 Unix UID 校验。
本机 root 和 hermes 运维权限不属于不可信隔离边界。

独立执行服务使用 `douyin-runner` 用户、单独虚拟环境及持久 profile，
通过 `/run/hermes-douyin/login.sock` 提供固定操作，检查 `SO_PEERCRED`。
不暴露浏览器调试 TCP、VNC、任意 URL、JavaScript、文件读写或 Cookie 导出接口。
原始浏览器登录凭据不进入源码、日志、Hermes 提示词和本机素材库。

独立服务使用 systemd `Type=notify`，套接字就绪后由 Python 上报真实 `MAINPID`，
并将通知权限缩回主进程、从子进程环境移除通知地址。同步 `ExecStop` 调用
`service.py --stop $MAINPID`，使用 pidfd
核对同用户、相同服务命令的主进程，发送 SIGTERM 并等待最多 40 秒，给持久上下文
保存及关闭的机会。`KillMode=mixed` 在其后清理残余进程；不先向 Chromium 整组发退出信号。
要求 systemd 254 或更新版本，安装器在修改系统前校验此条件。

## 部署入口

先提交、推送并确认 GitHub main，再将服务器源码快进至同一提交。root 使用
Hermes venv Python 执行 `ops/douyin-login/install.py --expected-account <已核实抖音号>`，
安装独立 venv、Debian Chromium、Xvfb 和服务；再执行 `--activate-plugin`
配置用户插件和 QQ 工具组，待当前代理空闲后重启网关。不要把 Cookie 当作该参数。
激活步骤按 YAML 解析后保存，仅增加这两个列表项，但会重新排版并移除 YAML 注释。
部署验收须比较配置语义，不以文件逐字节相同作为该文件的判断依据。

安装器内部以 `--system`、`--gid`、`--home-dir`、`--shell` 创建隔离账号，
仅将 hermes 追加进套接字访问组；以 `systemctl enable --now` 启动独立服务。
它不执行系统整体升级，不修改其他服务配置；浏览器依赖安装仍会增加
共享系统库，应先核对磁盘、内存和包管理器状态。重复运行不会清空 profile。
APT 使用 `--no-install-recommends`，不为无桌面的服务器增装打印机、设备发现等推荐服务。
浏览器固定使用 `/usr/bin/chromium`，来自 Debian 的 `chromium` 与
`chromium-sandbox` 包，Playwright 仅作为驱动。首次部署的官方浏览器下载链路过慢，
因此不依赖 Google 下载；需以真实启动和页面测试验证此组合，不关闭 Chromium 沙箱。

检查 `hermes-douyin.service`、`hermes-gateway.service`、实际工具 schema 和 QQ 连接。
回滚时停用独立服务并从配置移除这两个新增列表项，撤掉专属网关 drop-in；
不要覆盖原有插件、工具组、SOUL、记忆或会话。保留私有 profile 便于恢复。

二维码是短期登录凭证，插件缓存于 `$HERMES_HOME/cache/douyin-login/`，权限私有；
下次生成二维码时清理超过十分钟的同类二维码。服务端浏览器 profile 是有效运行数据，
不能作为测试残留删除。QQ 已投递图片及聊天历史不随文件清理而撤回。

## 验证边界

### 临时人工验证窗口

仅在阿颜当次明确允许时，由运维临时提供 noVNC 人工窗口。首次服务器扫码已观察到
“接收短信验证码 / 验证登录密码 / 发送短信验证”的设备验证选择，它不是已登录状态，
手机端不一定另有提示。不要自动触发短信，不让模型接收登录密码或验证码。

窗口使用 Debian `x11vnc`、`novnc`、`websockify`，安装时不包含推荐组件。
VNC 与 WebSocket 分别只监听 `127.0.0.1:5905`、`127.0.0.1:6085`，关闭 IPv6
监听，设置临时 VNC 密码；Windows 经 SSH `127.0.0.1:16085 -> 127.0.0.1:6085`
转发后，在本机浏览器打开 noVNC。密码不写 URL，抖音验证码由阿颜自己在网页输入。
两个临时 systemd 单元设 `RuntimeMaxSec=15min`，不设开机启动；验证完成或超时后
关闭转发、服务及密码文件，不在公网开远程桌面端口。
运维入口为 `ops/douyin-login/manual_window.py open|close`；可选包用
`apt-get install --no-install-recommends x11vnc novnc websockify` 安装。
启动器以 `--unit`、`--property` 创建临时单元，经 `--target` 进程的 `--mount`
命名空间连接现有显示；websockify 的 `--web` 只服务 noVNC 静态文件，不导出运行目录。
重复开启前以 `systemctl is-active --quiet` 检查旧窗口，已有窗口时拒绝覆盖；
关闭后核实两个服务都不活跃，再宣布入口已关闭。
启动就绪同时要求端口可连接、对应单元为 active，并通过内核 TCP socket inode
确认监听者位于该单元的 cgroup；不把无关服务占用的端口误认作本次窗口。

人工验证仅控制已有独立浏览器，不重启、不切换 profile。结束后再验证账号与重启
持久性。临时窗口当前依赖本机 SSH 转发，不宣称它可以在 Windows 离线时从 QQ 打开；
常规扫码和登录状态工具仍在服务器运行，额外验证须另行人工接管。

一次只保留一个 VNC 客户端。切换到系统 Chrome/Edge 前，先断开 Codex 内置窗口；
否则即使临时口令正确，新连接也可能因旧客户端独占而被拒绝。内置窗口无法传递
键盘时使用系统浏览器；noVNC 左侧 Clipboard 不是抖音输入框，本通道禁用剪贴板同步。

### 当前验收结果

2026-10-22，阿颜经临时 Chrome 窗口完成设备验证，窗口和 SSH 转发随后关闭。
实际 Hermes 插件经 Unix socket 检查服务器浏览器，返回 `logged_in` 且预期账号匹配。
同步停止后服务退出码为 0、隔离用户无残留进程；重新启动并再次走同一工具链路，
仍返回正确账号已登录。真实浏览器驱动的关闭诊断也记录退出码 0。
已有 profile 的旧 `exit_type` 标记仍为 `Crashed`，没有修改该字段来伪造验证结果；
不以它单独判定当前进程是否正常退出，更不据此清空有效登录目录。

协议、权限、错误与页面状态判别的单元测试不等于真实 QQ 会话验收。
本阶段未通过真实 QQ 消息测试二维码的最终投递，也未调用模型、上传或发布视频。
登录不保证永久有效；抖音再次要求扫码或设备验证时，按实际状态进行人工处理。

Playwright 持久上下文与登录安全依据：
[持久上下文](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)、
[登录状态保护](https://playwright.dev/python/docs/auth)。
