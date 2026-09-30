# PLAN-067f：Vue 试点组与观察窗口

状态：**进行中 · 观察窗口自 2026-09-30T13:52Z 开始**

## 目标

在真实试点用户完成 OIDC 登录、回调和工作台基本流程后，至少观察一个发布窗口/24 小时，再决定是否推进 Gradio 退役评估。观察期不改变根路径，不卸载任何旧模块。

## 试点范围

- Authentik 组：`qyunslation-vue-beta`。
- 服务端 capability：`workbench_v2`。
- 试点用户必须由管理员明确加入该组；不得把普通用户或管理员权限作为默认试点身份。
- 真实验收步骤：登录 → `/api/v1/me` → `/next/workbench` → 退出 → 再次访问受保护路径；记录浏览器未收到 OIDC access/refresh token，BFF cookie 为 Secure/HttpOnly/SameSite=Lax。

## 观察指标

- Authentik 登录/回调失败率和 4xx/5xx。
- sidecar `/api/v1` 5xx、OIDC discovery/token exchange 错误。
- Caddy upstream connection/reset 错误。
- `/next` 前端异常、任务创建/查询失败、Gradio 根入口可用性。
- 试点用户反馈：翻译任务是否仍能上传、预检、下载，旧任务是否可查。

## 停止与回滚

- 出现跨租户、认证绕过、根入口异常、旧任务/下载回归或持续 5xx 时立即停止观察并恢复上一个 Caddy 配置提交；不删除数据库数据，不重复执行运行中任务。
- 观察窗口结束前不能卸载 Gradio、`pdf2zh.service`、归档 watcher、受保护下载或旧复核资源。
