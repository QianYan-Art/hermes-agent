# 源码架构与维护边界

常用叫法：源码梳理、架构地图、模块职责、调用链、耦合、重复逻辑、维护风险、源码审查。

本轮审查日期为 2026-10-23，起点为 `main` 的
`b8d7167a75a5fbe04927fb9b57d140c67dbac4b9`，初始工作区干净。
范围是 QQBot 日常运行链和保留的辅助服务；2026-10-23 的本地审查阶段没有提交、
推送、部署或重启生产服务。2026-10-24 经授权继续发布收尾，发布状态在末节单独维护；
本地回归记录本身不代表真实平台行为已验收。

## 架构地图

| 边界 | 职责与关键入口 | 维护约束 |
| --- | --- | --- |
| QQ 入站 | `gateway/platforms/qqbot/adapter.py:816` 解析事件，按消息类型构造 `MessageEvent`；`gateway/platforms/base.py:3993` 处理活动会话和控制命令 | 适配器负责协议、收发和平台身份，业务会话状态交给 runner |
| 授权与命令 | `gateway/run.py:7387` 进入授权、忙碌/普通命令分派；`_check_slash_access` 共享权限规则 | 两层控制命令快速路径各有用途，不能删掉其中一层审批/停止通道 |
| 会话与模型覆盖 | `gateway/session.py:600` 的 `build_session_key`；`gateway/run.py:10122` 的会话边界处理；`_resolve_session_agent_runtime` 解析会话运行时 | `/reset` 与 `/new` 的历史、模型覆盖和安全状态语义不同，继续共用既有边界处理器 |
| 主对话 | `run_agent.py` 的 `AIAgent` 为兼容入口；实际初始化、循环、压缩分别在 `agent/agent_init.py`、`agent/conversation_loop.py`、`agent/conversation_compression.py` | 已有拆分承担真实职责，不能只按文件长度继续拆入口 |
| 模型与辅助请求 | `hermes_cli/runtime_provider.py:1228` 解析认证和端点；`providers/base.py` 与保留 provider 插件提供能力；`agent/transports/` 负责协议；`agent/auxiliary_client.py` 负责辅助任务解析、缓存、重试 | 显式会话运行时优先于全局默认；主模型 transport 与辅助 transport 不可凭模型名称混用 |
| 图片、视频、附件 | QQ 入站缓存→runner 媒体缓冲→`agent/image_routing.py` 决策/编码→transport；出站由 runner 和 BaseAdapter 解析工具媒体，再由 QQ 适配器发送 | `agent/kimi_code.py` 是 Kimi 官方端点规则源；原生视觉与辅助摘要、视频与普通文件分别保留现有边界 |
| 人格、提示、技能 | `agent/system_prompt.py` 组装基础规则；`agent/prompt_builder.py` 加载身份、上下文与技能目录；conversation loop 固定会话快照 | 角色卡定义身份，角色 skill 提供资源；没有证据要求重写人格或每轮重建提示 |
| 插件与工具 | `tools/registry.py`→工具注册→`model_tools.py` 定义与派发→`agent/tool_executor.py` 执行；`hermes_cli/plugins.py` 管生命周期与 hook；`tools/delegate_tool.py` 约束子代理 | 保留注册入口、工具范围和内建审批；插件不得直接修改核心文件 |
| 抖音与 OpenFilm | `ops/douyin-login/sync_openfilm.py:157` / `:322` 校验并经 SSH/SCP 交付→`ops/douyin-login/stage_release.py:288` 原子安装→`ops/douyin-plugin/__init__.py`→UDS 服务→`content.py` | 制作交付、浏览器执行、本人确认分别负责；导入、stage、暂存和公开发布不能混为一项成功 |

常规 QQ 调用链：`QQAdapter` → `BasePlatformAdapter.handle_message` →
`GatewayRunner._handle_message` → `_handle_message_with_agent` → `_run_agent` →
`AIAgent.run_conversation` → transport / 工具派发 → 平台发送。

抖音流程：作品入库 → 封面选择 → `prepare` 绑定物料与账号 → `stage` 核验实时编辑页 →
`editor_ready` → 本人私聊精确确认 → gateway MainPID 校验 → `publish`。
结果未知时保留 `commit_attempted`，禁止自动重提；重启会使内存预览证明失效。

## 本轮局部修复

下列项按风险排序。源码位置指本轮实现入口，测试是本地隔离测试，不调用真实平台。

| 等级 | 已确认问题与调整 | 回归入口 |
| --- | --- | --- |
| P1 | 抖音启动按随机 UUID 文件名只取最后 1000 条，可能漏载未知发布提交，使防重门禁看不到旧记录。`ops/douyin-login/content.py:195` 改为加载全部有效持久任务，不引入自动删账策略 | `tests/ops/test_douyin_content.py:404`：超过 1000 条、低排序未知提交、重启后不同文案仍拒绝重提 |
| P2 | 固定上传入口只限制请求 URL，未限制重定向后的页面；上传控件等待期间也可能跳转。`ops/douyin-login/content.py:251`、`:633` 在导航完成与本地文件交给页面前均校验合法地址 | `tests/ops/test_douyin_content.py:120`：外站重定向、等待控件后跳转不得调用上传 |
| P2 | 子代理按工具集名过滤漏掉 `messaging`，组合工具集也可重新带入禁用工具。`tools/delegate_tool.py:55` 集中禁用集合，`:905` 的 child 构建用已有 `disabled_toolsets` 做最终减法；同时继承父级禁用项，保留 orchestrator 单独授予 delegation 的规则 | `tests/tools/test_delegate_toolset_scope.py:143`：父级 messaging、组合工具集、leaf/orchestrator 工具范围 |
| P2 | 非 vision 的普通异步辅助请求遗漏向客户端解析、自动回退和重建传递 `main_runtime`。`agent/auxiliary_client.py:5667`、`:2938` 为这条路径补齐与同步入口一致的传递链；vision 专用解析器仍属下文待处理范围 | `tests/agent/test_auxiliary_request_isolation.py:19`：普通请求的不同会话缓存、自动回退、认证恢复 |
| P2 | 同步、异步容量错误后的主模型兜底重读全局模型，丢失显式会话端点和凭据。`agent/auxiliary_client.py:3108` 的 `_try_main_agent_model_fallback` 优先采用传入运行时，保持原有回退顺序 | 同文件测试：两条请求路径的容量错误兜底及命名 custom 运行时 |
| P2 | 媒体侧独立实现 Kimi 端点判定，与请求侧对空 userinfo URL 的结果不同。`agent/image_routing.py:45` 改用 `agent/kimi_code.py:10` 的统一函数，保留图片/视频模型范围 | `tests/agent/test_kimi_native_media.py:74`：正常端点、相似主机、端口、query、空 userinfo、图片视频能力 |
| P2 | Playwright 驱动已启动、浏览器尚在启动时被取消，`except Exception` 不会捕获 `CancelledError`。`ops/douyin-login/service.py:411` 的取消分支先回收部分资源，再传播取消 | `tests/ops/test_douyin_login.py:820`：直接取消、服务超时、驱动回收、再次懒启动 |
| P3 | 作品清单默认文案绕过 prepare 请求的控制字符校验，可能入库后在页面填写时失败。`ops/douyin-login/releases.py:55` 对齐非法字符边界，不限制正常中文文案 | `tests/ops/test_douyin_releases.py:135`：标题换行/NUL、简介 NUL |
| P3 | `agent/auxiliary_client.py:5035` 的 `_build_call_kwargs` 浅拷贝后向调用方 tags 列表追加内容，重试会累积。改为构建新列表；不恢复已裁剪的 provider | `tests/agent/test_auxiliary_request_isolation.py:99`：输入不变，两次构建不重复追加 |

上述新增辅助请求隔离与委派范围回归纳入 `tests/trimmed_manifest.py`。
仓库 `AGENTS.md` 的测试说明同步到现行 runner，移除了已过期的 xdist、逐测试隔离插件和
`--no-isolate` 用法；这是文档纠错，没有改测试执行机制。

## 尚需确认的修复与维护风险

这些不是本轮已修复项。优先级根据可触发的影响排序；明确改变协议或生命周期的方案须另行确认。

1. **P1，QQ 旧审批按钮可误解后续请求。**
   `gateway/platforms/qqbot/keyboards.py:204` 仅携带 session key 与决定；
   `gateway/platforms/qqbot/adapter.py:1293` 按会话调用 resolver；
   `tools/approval.py:615` 默认取队列首项。请求 A 超时移除、请求 B 入队后，点击 A 的旧按钮可解决 B。
   操作者身份检查仍在，问题是确认对象不绑定，不能宣称任意人可绕过审批。
   方案：每条 `_ApprovalEntry` 分配不可复用请求 ID，通知、按钮和 resolver 贯通 ID；
   按钮仅解决匹配请求，旧格式按钮失败关闭；`/approve` 的既有 FIFO/显式 all 语义独立保留。
   验收应覆盖过期、reset 后旧按钮、同会话乱序多请求与原操作者限制。
   这会扩展审批通知与 QQ 回调数据契约，本轮未擅自修改。

2. **P1，并发辅助路由仍依赖进程级全局。**
   `agent/conversation_loop.py:417` 每轮调用 setter；
   `agent/auxiliary_client.py:1886` 的五个 `_RUNTIME_MAIN_*` 保存模型、端点和凭据；
   `tools/web_tools.py:297` 的取客户端路径未显式传会话运行时。
   另行执行的独立 Python 进程两线程取证中，A 写入 `session-a`，B 写入 `session-b` 后，A 读回 `session-b`；
   这份证据来自独立手工实验，不是新增 pytest 用例，复现代码与输出记录在本轮 `.mission` 日志。
   这是状态竞争复现，未发送外部请求，不能升级为生产串线事故证明。
   本轮补齐显式参数路径仍不能消除所有隐式读取。
   特别是 `agent/auxiliary_client.py:4239` 的 `resolve_vision_provider_client` 尚无
   `main_runtime` 参数，同步/异步 `task="vision"` 的首次解析和同 provider 重建仍依赖隐式状态；
   本轮普通请求隔离回归不覆盖该专用解析链。
   方案：以会话/任务 ContextVar 保存一次完整运行时，在线程池边界显式传递上下文，
   子代理和 cron 独立绑定；auto 缓存键使用同一快照，退出时恢复 token。
   不采用“轮末清空全局”的修法；那仍会竞争。需要先确认隔离及继承规则再实施。

3. **P2，插件加载失败与 force reload 的注册生命周期不完整。**
   `hermes_cli/plugins.py:354` 直接写工具 registry，`:920` 写 hook；
   `:1019` 强制重载清 manager 记录，`:1402` 开始的加载失败路径未按归属撤销已注册项。
   失败插件可留下部分注册，重载禁用插件可能仍留下工具。
   方案：按 plugin ID 追踪注册归属，事务暂存，成功后提交，失败/卸载按归属撤销；
   不清空共享 registry，以免破坏核心及其他插件。应先确定重载及同名工具覆盖契约。

4. **P2，共享群会话的 QQ 审批按钮失败关闭。**
   `gateway/session.py:649` 在 `group_sessions_per_user=False` 时省略用户 ID，
   `gateway/platforms/qqbot/adapter.py:1220` 的群按钮授权却要求该 ID。
   不能为了可用性删除操作者检查。应先确定由请求发起者、管理员还是其他指定身份审批，
   再将身份随请求保存并测试；当前问题不构成未授权放行。

5. **P2，策略型插件 hook 与观察型 hook 共用异常策略。**
   `hermes_cli/plugins.py:1531` 的 `invoke_hook` 记录回调异常后继续；
   `model_tools.py:990` 等调用方也继续执行。仅靠插件自定义策略的限制故障时可能放行。
   内建审批另有路径，不能据此断言内建门禁失效；RTK 明确要求故障放行，也不能一律改为拒绝。
   方案：显式声明强制策略 hook，并仅对这类 hook 的异常拒绝执行；须先确认插件 API 与兼容策略。

6. **P3，进程内缓存与单实例假设需明确。**
   `agent/prompt_builder.py:1099` 的技能目录 LRU 命中早于磁盘 manifest 校验，外部直接修改技能文件后
   可能继续看到旧目录；不能通过每轮重建系统提示解决，应规定新会话/显式刷新时的失效规则。
   `gateway/run.py:1825` 的单一 runner 弱引用被 `tools/send_message_tool.py:539` 使用；
   单 runner 部署符合当前假设，多 runner 同进程须先设计实例路由。
   辅助客户端 cache 在锁外构建、异步 loop 不属于键，也值得做双 loop 并发构建验证；
   本轮仅静态识别该竞争窗口，未将其宣称为已复现缺陷。

## 有意保留的边界

- BaseAdapter 与 runner 的双重控制命令通道、插件与 UDS 服务的双重输入校验、
  prepare/stage/publish 的逐层安全检查，各自覆盖不同信任边界，不能按“重复”删除。
- 主模型请求和辅助请求有不同生命周期；优先共享小范围协议规则，不能把所有重试和客户端强行合并。
- 未因 `gateway/run.py` 或 `run_agent.py` 大就提出大拆分。建议先处理上面的请求身份、运行时作用域和插件归属，
  再根据稳定接口考虑模块拆分。
- 对 347 个核心及相邻模块做了静态顶层 import 图检查，共 450 条边；唯一多节点分量为
  `agent.lsp` 与 `agent.lsp.manager` 的包/子模块引用。该残留面不属于本轮 QQ 精简修复目标，
  没有据此认定启动循环错误，也未恢复 LSP。函数内延迟导入和动态插件不在此静态图的证明范围内。

## 验证与证据边界

Windows 使用项目虚拟环境运行正式入口和定向回归；定向 pytest 的
`--timeout-method` 参数设为 `thread`，避免默认 POSIX signal 超时在 Windows 上不可用：

```powershell
.venv/Scripts/python.exe scripts/run_trimmed_tests.py
.venv/Scripts/python.exe -m pytest tests/agent/test_auxiliary_request_isolation.py -q --timeout-method thread
```

- 修复前正式精简 profile：1694 通过、14 跳过。
- 本轮辅助请求及既有认证/凭据恢复定向回归：57 通过；媒体、transport 与网关视频定向回归：181 通过。
- 浏览器取消资源回归及现有登录服务测试：55 通过，使用假 Playwright 驱动，未启动真实浏览器。
- 作品状态、导航和清单回归：92 通过、5 跳过；加载全部任务会增加启动读取量，后续若优化容量应先建立不丢未决提交的索引契约。
- 子代理范围及异步委派定向回归：14 通过；使用真实 AIAgent 工具构建链，模型客户端替换为假对象。
  首轮 fixture 曾漏拦 `example.invalid` 的上下文长度探测并回退，随后修正对应函数引用；后续不再触发该探测，没有真实模型请求。
- 最终正式精简 profile（含编译检查）：**1722 通过、14 跳过**，311.12 秒；
  本轮修改的全部 Python 文件 Ruff 通过，`git diff --check` 通过。另补跑既有辅助回退分层与 extra-body 回归 8 项通过。
  新增普通请求隔离与委派工具范围均已进入正式清单；没有扩大到已裁剪上游功能的全量测试。
- 新回归先在修复前得到失败，再在修复后通过。外部模型、SSH/SCP 与网页行为使用现有 fixture/mock；
  本轮未做真实 QQ 收发、真实抖音上传/发布、模型高速版、大型视频和超长上下文端到端验收。
- 没有新的签名头或密码学验签证据，不宣称响应已通过密码学验签。
- `.mission/finish-kimi31-cleanup-20261023.ps1` 在本轮核对的父目录与源码仓库任务目录中均未找到；
  仅凭缺失不能判断阿颜是否已执行。未重建、执行或绕过此前被拒绝的清理操作，旧任务材料未动。
- 2026-10-23 本地审查阶段未写入 KBase、运行记忆、会话、凭据和生产配置。
  本地恢复工件位于 `.mission/`，不作为运行时依赖；随后授权的发布另见末节。

2026-10-23 文档审阅临时包的删除命令被执行策略拒绝，仅返回 `blocked by policy`，无细分原因。
没有改换工具重试删除；六个目录保留在仓库 `.doc-maintenance/runs/` 下：
`1792811877812`、`1792811948997`、`1792812605791`、`1792812770019`、`1792812939100`、`1792813245259`。
它们均为本轮生成、被 Git 忽略的审阅材料，非运行依赖；该项清理尚未完成，需人工处理。

## 2026-10-24 发布收尾

- 本次明确授权提交、推送、部署，并更新开发文档、KBase、locator 与 nmem。
  辅助路由/委派边界提交为 `04aa145`，抖音账本/上传/取消回收提交为 `15b06f1`。
- 主代理重新执行正式精简验证（包含编译）：1722 通过、14 跳过，JUnit 无失败或错误；
  13 个修改 Python 文件 Ruff 与 `git diff --check` 通过。
- 此轮新子代理因工作区额度不足未能执行，未换模型重试。主代理复核实际 diff、关键
  调用方和回归；原本 2026-10-23 的独立审查仍仅代表它当时的审查，不冒称新增独立验收。
- 部署前先核对无活动 agent、无活动抖音任务和有效待确认计划；仅将 token 压缩阈值
  从 95% 改为 90%，保留 `k3.1-pro`、`low`、262144 和其余配置。
  本节当前为已提交准备发布，生产核验完成后再补记运行结果。
- 缓存时长、订阅额度窗口与压缩阈值的区别见 `07-server-operations.md`；
  nmem 优先原位更新主条目，不将运行记忆或旧会话作为清理对象。
