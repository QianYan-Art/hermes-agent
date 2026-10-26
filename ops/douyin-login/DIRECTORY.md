# 抖音运行目录

数据根目录为 `/var/lib/hermes-douyin`，有效数据不是临时文件。

- `releases/<期号>/`：原成片和清单，同编号不覆盖不同内容。
- `covers/<期号>/uploads/<封面ID>/`：本人上传图片。
- `covers/<期号>/frames/<封面ID>/`：视频提帧。
- `covers/<期号>/reused/<封面ID>/`：从持久库为目标作品重新绑定的封面。
- 每组封面包含 `source.jpg`、`landscape.jpg`（4:3）、`portrait.jpg`（3:4）及 `cover.json`。原图是已规范化副本；不要直接编辑或覆盖这些文件。
- `content-jobs/`、`content-plans/`：任务、计划、引用与防重数据。结果未知的提交不能删除、清零或重投。
- `chromium-profile/`：账号登录与浏览器持久资料，不能当作缓存整体清理。
- `.cache/`、`.config/`、`.local/`：浏览器及虚拟显示运行资料；仅清理经过核实的可再生缓存。

在指定 QQ 私聊说“查看封面库”，Hermes 用 `cover_library` 分页展示。
本人选择后，`cover_reuse` 校验原图并为目标期号生成对应 ID，再预览、确认和准备。
跨期不能直接套用源封面 ID；封面复用不触发上传或发布。

旧 `covers/<期号>/<封面ID>/` 仍兼容。分类迁移不改图片、ID 和清单；不能同时保留同 ID 的多份目录。
更完整的参数、发布确认与故障边界见 Hermes 仓库 `docs/tangyuge-hermes/10-douyin-publishing.md`。
