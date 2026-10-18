# qyunslation 与 QyunsApps 的边缘 / 身份合同

> PLAN-077 T1 · 2026-10-18 · 机器可读版：`tests/contracts/qyunsapps-contract.json` · 对账：`tests/contracts/test_qyunsapps_contract.py`

## 归属

| 对象 | 活动 SSOT | 本仓保留什么 |
| --- | --- | --- |
| `translate.qyunsgen.com` / `office.qyunsgen.com` 的 Caddy 站点 | QyunsApps `infra/edge/sites/translate.caddy`（PLAN-002b，生产已于 2026-10-18 切换） | 本合同（路由、上游、超时、安全头）；改路由须开跨仓计划 |
| Authentik `qyunslation` provider / application / scope mapping | QyunsApps `authentik/blueprints/qyunslation-oidc.yaml`（PLAN-002d） | `deploy/authentik/blueprints/` 作为迁移基线，见该目录 README |
| BFF、会话、CSRF、Vue 页面、业务 PG、归档 | 本仓 | 全部 |

## 边缘路由（上游均为 sidecar `127.0.0.1:8010`）

| 路径 | 行为 | 超时（读/写） |
| --- | --- | --- |
| `/` | 302 → `/next/` | — |
| `/next`、`/next/*` | 反代，gzip | 60s / 60s |
| `/app-assets/*` | 反代，`Cache-Control: public, max-age=31536000, immutable` | 默认 |
| `/auth`、`/auth/*` | 反代，`Cache-Control: no-store` | 30s / 30s |
| `/api/v1`、`/api/v1/*` | 反代，gzip（翻译任务较长） | 120s / 120s |
| 其他 | 302 → `https://translate.qyunsgen.com/next/` | — |

安全头：HSTS、`X-Content-Type-Options: nosniff`、`X-Frame-Options: SAMEORIGIN`。`office.qyunsgen.com` 只做 302 到 translate 的 `/next/`。

## OIDC 客户端

- issuer `https://auth.qyunsgen.com/application/o/qyunslation/`，client_id `qyunslation`，回调 `https://translate.qyunsgen.com/auth/callback`。
- scope：`openid profile email tenant roles`；`roles` 里的 `workbench_v2` 来自 Authentik 组 `qyunslation-vue-beta`。
- 会话：空闲 60 分钟、绝对 12 小时（可由 `QYUNSLATION_SESSION_IDLE_MINUTES` / `QYUNSLATION_SESSION_ABSOLUTE_HOURS` 覆盖）；cookie `qyunslation_session`，CSRF cookie `qyunslation_csrf`。
- client secret 不入库；Authentik 侧由蓝图之外管理（蓝图不含 `client_secret`）。

## 退出

1. 页面里的"退出登录"：`POST /auth/logout`（`X-CSRF-Token` = `qyunslation_csrf`）撤销 `WebSession`，随后整页跳到 Authentik end-session `https://auth.qyunsgen.com/application/o/qyunslation/end-session/`。开发环境（`import.meta.env.DEV`）不跳转，仍回本地登录页。
2. 平台退出链：`/next/qyuns-logout?next=<url>`。在应用启动最前面处理（早于任何 `/api/v1/me` 请求，避免会话已过期时被 401 带去登录页），先 `POST /auth/logout`（3 秒超时，失败也继续），再跳 `next`；没有 `next` 时跳 end-session。
3. `next` 白名单：主机 `apps / watch / weknora / translate.qyunsgen.com`，或 Authentik 的 `/application/o/<slug>/end-session/`；其余一律拒绝（页面显示提示、不发任何请求、会话保持不变）。
4. Authentik 2025.10 的 end-session 不支持 `post_logout_redirect_uri`，所以最终会停在 Authentik 的"已退出"页；要回到门户，靠各应用的退出路由逐环串联。

## 顶栏

`<qyuns-appbar current-app="translate" theme="light">`，只在 `translate.qyunsgen.com` 且已登录时挂载；`VITE_QYUNSAPPS_APPBAR=false` 可关闭。脚本 `/app-assets/qyuns-appbar.js`（随 `static/app` 发布，同源）。令牌文件 `frontend/src/next/vendor/*` 带 `generated from QyunsApps@<sha>` 头与 `qyunsapps-vendored.json` 校验和，用 QyunsApps `sync-vendored.sh --check` 检漂移，不要手改。

## 变更规则

改以上任何一行：先在本仓改合同 + 测试，再在 QyunsApps 开计划改站点/蓝图，两边互相引用；不要只改一边。
