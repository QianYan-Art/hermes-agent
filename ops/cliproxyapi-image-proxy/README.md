# CPA 图片终态兼容补丁

本目录只维护与 Hermes 生图集成有关的一条外部旁路兼容规则，不包含 CPA 主程序、
配置、账号或私钥。124 的图片旁路目前是独立 Go 源码目录，不是 Git 仓库，
因此将可审查补丁随本项目提交、推送后再应用，不能先热改生产源码。

## 边界

`codex-image-compat.patch` 允许 `gpt-image-2.5-flare` 与
`gpt-image-2.5-sunburst` 接收上游声明的 `gpt-image-2-codex` 图片；
原 `gpt-image-2` 行为不变。其他不匹配的型号、缺少完成事件、空图片及真实
上游错误仍按原逻辑报错。不修改编排模型、路由、鉴权或 usage。

这不是把 Codex 图片标记为真实 2.5 模型：请求名称和实际执行模型应分别理解。
Hermes 也不因有效图片的返回模型名不同而拒绝，响应携带 `model` 时记录为
`upstream_model`。

## 适用基线

服务器源码：`/root/cliproxyapi-image-proxy/src`。

- `main.go` 原 SHA-256：
  `73b2212115d37324eea95ced41a456178b32105a090dad09690bcd9f57f9add8`
- `main_test.go` 原 SHA-256：
  `93743a8c30782de0775e6ceaebcb9c04f410b3e05a79de95734af77c9ae91a7b`
- 依赖沿用该目录的 `go.mod` / `go.sum`，不升级依赖。

应用前核对基线并执行 `git apply --check`；不匹配就停止，不强制覆盖。
在隔离副本应用补丁，执行 `go test -count=1 ./...` 和 `go vet ./...`，
再以 `CGO_ENABLED=0 GOOS=linux GOARCH=amd64` 编译候选二进制。
仅在相关提交已推送并核实远程、图片旁路无在途请求时，原子替换二进制并重启
`cliproxyapi-image-proxy.service`。配置和账号保持原位；健康与真实生图通过后
才移除本轮候选及临时回滚副本。
