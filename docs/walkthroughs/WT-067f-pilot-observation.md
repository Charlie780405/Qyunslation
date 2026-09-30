# WT-067f：Vue 试点观察窗口启动证据

对应计划：[PLAN-067f](../plans/PLAN-067-workbench-public-cutover/PLAN-067f-pilot-observation.md)

## 启动基线

- 观察起点：`2026-09-30T13:52Z`。
- qyunsgen main：`eb15b57d`；Caddy 容器已重建且配置校验通过。
- sidecar：`qyunslation-office.service` 为 `active`，`/api/v1/health` 返回 200 且数据库状态为 `ok`。
- 公网探针：`/next/login` 200、`/app-assets` 200 且 immutable、`/api/v1/me` 无认证 401、`/auth/login?format=json` 200；根路径 200 且仍为 Gradio。
- 最近 10 分钟 sidecar 无 `error/traceback/failed/exception`；Caddy 仅有既有 Origin Certificate OCSP stapling warning，无 upstream 错误。

## 待人工验收

- 由管理员确认一名 `qyunslation-vue-beta` 试点用户。
- 用该用户完成真实浏览器 OIDC callback、BFF cookie、`/api/v1/me.capabilities.workbench_v2`、logout 和跨租户拒绝检查。
- 记录至少一个发布窗口/24 小时的指标后，才进入 067g Gradio 退役与冗余模块审计。
