# PLAN-067d：登录会话、Vue 试点 capability 与 CSRF 验收

状态：**代码门禁已完成 · 生产验收等待 067c/DNS**

## 目标

让 Authentik 试点组以服务端声明授予 `workbench_v2`，并让 Vue 路由、BFF 会话和 `/api/v1/me` 对该 capability 使用同一事实源。

## 实施内容

- Authentik `roles` scope mapping：`qyunslation-vue-beta` 组成员获得 `workbench_v2`；其它用户不获得。
- BFF 请求 `roles` scope，并在服务端白名单中保留 `workbench_v2`。
- `/api/v1/me.capabilities.workbench_v2` 只由认证上下文生成，不能由请求体或浏览器存储覆盖。
- Vue 非开发预览路由要求 `workbench_v2`；试点组外用户看到明确的无权限提示并保留 Gradio 回退入口。
- 保持 PKCE、state、nonce、HttpOnly session、双提交 CSRF、logout 撤销和安全 `return_to`。

## 自动化门槛

- BFF 登录 query 必须包含 `roles` scope 和 `/auth/callback`。
- 模拟 Authentik callback 后，`/api/v1/me` 返回 `workbench_v2=true`，持久化角色不被 capability 冒充。
- 缺失 CSRF 返回 403，正确 CSRF 可以写入偏好，logout 后会话撤销。
- Vue route guard 对非试点账号拒绝进入工作台。
- `npm --prefix frontend run type-check`、`npm --prefix frontend run build` 通过。

## 生产门槛

只有以下条件全部满足才可关闭本子计划：

1. `verify-plan-067b.sh` 无 BLOCKED/FAIL。
2. `inject-plan-067c-bff-env.py --apply` 成功且 sidecar 已重启。
3. 真实试点账号完成登录、回调、`/api/v1/me`、登出和 CSRF 验收。
4. 浏览器未看到 token，Cookie 属性和跨租户拒绝均有证据。

