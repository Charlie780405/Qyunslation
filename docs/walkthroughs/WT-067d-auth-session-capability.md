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

## 生产缺口

- `auth.qyunsgen.com` 仍未解析，067b 门禁为 BLOCKED。
- 067c 尚未 apply，`office.env` 未写入 client ID/session key，sidecar 未因本切片重启。
- 尚未执行真实浏览器 OIDC callback、`/api/v1/me`、登出和 CSRF 证据。

因此本子计划只能标记“代码完成、生产验收未完成”，不得进入 Vue 公网灰度。
