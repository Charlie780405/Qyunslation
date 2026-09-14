# PLAN-060b：工作台签名桥接与运行持久化

> 父计划：[PLAN-060](./README.md)

- Gradio callback 使用 `request.username` 作为用户 subject；浏览器不提供租户、项目、角色或词库版本。
- GUI 进程以时间戳、随机数、方法、路径和原始请求体 SHA-256 构造 HMAC；sidecar 仅接受 `127.0.0.1`/`::1`、60 秒内签名和未重放 nonce。
- `/internal/workbench/v1/*` 不属于公网 API，Caddy 不得代理。缺失桥接或签名失败只显示“专业词库暂不可用”，不写匿名共享库，也不让翻译主任务失败。
- `060a0001` 迁移创建一对一 `WorkbenchTranslationRun`，关联持久化 Job。
