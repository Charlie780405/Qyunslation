# WT-067e：Caddy Vue 灰度路由部署证据

对应计划：[PLAN-067e](../plans/PLAN-067-workbench-public-cutover/PLAN-067e-caddy-vue-gray-route.md)

## 变更证据

- qyunsgen 配置变更已精确提交：feature `8479bdce`，合并到 main 为 `eb15b57d`，远端已推送。
- Caddy 源配置与容器内 `/etc/caddy/Caddyfile` SHA-256 一致。
- `docker exec qyunsgen-caddy caddy validate --config /etc/caddy/Caddyfile`：`Valid configuration`。
- Caddy 仅重建 `qyunsgen-caddy`，容器启动正常；已保留部署前配置备份 `/tmp/Caddyfile-production-public.plan067e.20260930T135014Z.bak`。

## 路由验收

本机 `--resolve translate.qyunsgen.com:443:127.0.0.1` 与公网 Cloudflare 路径均通过：

| 探针 | 结果 |
|---|---|
| `/` | HTTP 200，仍返回 Gradio 登录页 |
| `/next/login` | HTTP 200，返回 Vue SPA |
| `/api/v1/health` | HTTP 200，`db=ok` |
| `/api/v1/me` 无认证 | HTTP 401，`missing Bearer token` |
| `/auth/login?format=json` | HTTP 200，返回 Authentik authorize URL、`roles` scope 和 `/auth/callback` |
| `/app-assets/*` | 由 sidecar 提供，immutable 缓存头已配置 |

## 未完成项

- 尚未使用真实 `qyunslation-vue-beta` 试点账号完成浏览器登录、OIDC callback、BFF cookie 属性、`/api/v1/me.capabilities.workbench_v2`、logout 和跨租户拒绝验收。
- 观察窗口从 `2026-09-30T13:52Z` 开始；窗口完成前不下线或卸载 Gradio。
