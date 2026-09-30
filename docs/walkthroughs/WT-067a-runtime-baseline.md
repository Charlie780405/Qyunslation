# WT-067a：运行时基线与切换契约证据

对应计划：[PLAN-067](../plans/PLAN-067-workbench-public-cutover/README.md)

## 本切片范围

仅冻结生产事实、UI/UX 附件适用性和 Authentik/BFF/Caddy 灰度契约；没有执行生产配置修改、服务重启、Caddy reload、数据库迁移或模块卸载。

## 证据摘要

- qyunslation `main` 与 `origin/main` 在 `931461e`。
- 当前公网根路径仍为 Gradio；sidecar 本地提供 `/next`、`/app-assets` 和 `/api/v1/health`。
- `/home/dev/pdf2zh/office.env` 缺少 `QYUNSLATION_OIDC_CLIENT_ID`、`QYUNSLATION_SESSION_KEY`。
- `auth.qyunsgen.com` 当前不能解析，生产 Caddy 也没有对应站点块。
- 生产 Caddy 尚未把 `/next`、`/app-assets`、`/auth`、`/api/v1` 转发到 `:8010`。
- PLAN-054 旧回调 `/oauth2/callback` 与当前 BFF `/auth/callback` 不一致。
- `office-archive-watch.service` 因缺少 `minio` 模块持续失败重启；不得作为冗余服务直接卸载。

## 结果

| 门项 | 结果 |
|---|---|
| 基线事实冻结 | PASS |
| 附件 UI/UX 决策冲突记录 | PASS |
| Authentik 公网可用 | BLOCKED，等待 067b |
| BFF 登录闭环 | BLOCKED，等待 client ID/session key |
| Caddy Vue 灰度 | BLOCKED，等待 067d |
| Gradio 退役 | NOT RUN，必须等待灰度观察和能力闭环 |
| 冗余模块安全卸载 | NONE CONFIRMED；需 067g 审计 |

## 下一切片缺口

067b 必须先处理：

1. Authentik `qyunslation` provider/application 与 `/auth/callback` 对齐。
2. `auth.qyunsgen.com` DNS、TLS 和 Caddy 站点可达性。
3. issuer、audience、JWKS、Allowed Origin 和试点组声明一致性。
