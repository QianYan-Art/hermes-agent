# 抖音服务器登录

常用叫法：抖音登录、抖音扫码、抖音账号状态、服务器抖音、OpenFilm 发布。

## 当前范围

第一阶段仅提供 `douyin_login` 工具：`action=status` 检查服务器页面，
`action=login` 在需要登录时取得二维码。没有上传、发布、作品删除、账号设置、
数据中心开通或统计接口。不能把本阶段称作“已经可以发布视频”。

普通个人号没有开放平台应用，本接入使用创作者中心独立浏览器，不宣称取得官方
发布 API 权限。Windows OpenFilm 工程和成品不自动上传、不整理；电脑离线时，
服务器不能读取仅存本机的视频。后续发布需要服务器可访问的成品和逐条确认。

## 使用

- 阿颜在指定 QQ 私聊说“检查抖音登录状态”，调用 `douyin_login(action="status")`。
- 说“登录抖音”时调用 `douyin_login(action="login")`，若返回 `media_tag`，
  必须在本次私聊最终回复中原样带上标签，QQ 才会投递二维码。不要转发至其他会话。
- 阿颜用抖音手机端扫码并确认后，再检查状态；二维码过期则再次请求登录。
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

## 部署入口

先提交、推送并确认 GitHub main，再将服务器源码快进至同一提交。root 使用
Hermes venv Python 执行 `ops/douyin-login/install.py --expected-account <已核实抖音号>`，
安装独立 venv、Debian Chromium、Xvfb 和服务；再执行 `--activate-plugin`
配置用户插件和 QQ 工具组，待当前代理空闲后重启网关。不要把 Cookie 当作该参数。
激活步骤按 YAML 解析后保存，仅增加这两个列表项，但会重新排版并移除 YAML 注释。
部署验收须比较配置语义，不以文件逐字节相同作为该文件的判断依据。

安装器内部以 `--system`、`--gid`、`--home-dir`、`--shell` 创建隔离账号，
仅将 hermes 追加进套接字访问组；以 `systemctl enable --now` 启动独立服务。
它不执行系统整体升级，不修改其他服务配置；Playwright 的系统依赖安装仍会增加
共享系统库，应先核对磁盘、内存和包管理器状态。重复运行不会清空 profile。
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

协议、权限、错误与页面状态判别的单元测试不等于真实登录成功。
服务器首次扫码后，还需检查正确账号、重启执行服务后保持登录；未完成时明确标记
待扫码或待人工验证。QQ 最终图片投递也须真实会话验收，工具返回路径不等于投递成功。

Playwright 持久上下文与登录安全依据：
[持久上下文](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)、
[登录状态保护](https://playwright.dev/python/docs/auth)。
