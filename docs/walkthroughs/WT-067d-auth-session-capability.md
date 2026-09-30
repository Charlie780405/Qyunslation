# WT-067d：登录会话与 Vue 试点 capability 证据

对应计划：[PLAN-067d](../plans/PLAN-067-workbench-public-cutover/PLAN-067d-auth-session-capability.md)

## 代码结果

- BFF 申请 `roles` scope，并白名单保留 `workbench_v2`。
- `/api/v1/me` 增加服务端生成的 `capabilities.workbench_v2`。
- Vue session store 增加 capability 查询；路由拒绝无 capability 用户，登录页显示中文无权限提示。
- Authentik provider 脚本增加 `roles` scope mapping：试点组成员才获得 `workbench_v2`。
- 已在本地 Authentik 执行幂等校正：roles mapping 存在，provider 共 5 个 scope mapping，strict callback 仍为 `/auth/callback`。

## 自动化结果

```text
.venv/bin/python -m pytest -q \
  tests/persist/test_plan066c_bff.py \
  tests/ui/test_plan066_next_surface.py -o addopts=''
6 passed

npm --prefix frontend run type-check  PASS
npm --prefix frontend run build       PASS（有既有大 chunk warning）
```

## 生产与本机预检结果

- 067b 已重跑并通过：`SUMMARY: PASS fail=0 blocked=0`。
- 067c 已 apply；`office.env` 和 0600 备份权限正确，未在证据中记录 secret；sidecar 已重启并为 `active`。
- 本机 `/auth/login?format=json` 返回 Authentik authorize URL，scope 含 `roles`，redirect URI 为 `/auth/callback`。
- 本机 `/api/v1/health` 返回 200；未认证 `/api/v1/me` 返回 401。
- 合成 cookie 的 logout 请求缺失 CSRF 返回 403，匹配 CSRF 返回 204；未触碰真实会话。

## 剩余生产缺口

- 尚未经过 Caddy 将 `/next`、`/auth`、`/api/v1` 灰度到 sidecar。
- 尚未使用真实试点账号完成浏览器 OIDC callback、`/api/v1/me` capability、cookie 属性、登出和跨租户拒绝证据。

因此本子计划标记为“代码与 sidecar 预检完成、真实浏览器验收待 067e 灰度路由”。
