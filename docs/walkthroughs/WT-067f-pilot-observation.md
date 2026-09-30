# WT-067f：Vue 试点观察窗口启动证据

对应计划：[PLAN-067f](../plans/PLAN-067-workbench-public-cutover/PLAN-067f-pilot-observation.md)

## 启动基线

- 观察起点：`2026-09-30T13:52Z`。
- qyunsgen main：`eb15b57d`；Caddy 容器已重建且配置校验通过。
- sidecar：`qyunslation-office.service` 为 `active`，`/api/v1/health` 返回 200 且数据库状态为 `ok`。
- 公网探针：`/next/login` 200、`/app-assets` 200 且 immutable、`/api/v1/me` 无认证 401、`/auth/login?format=json` 200；根路径 200 且仍为 Gradio。
- 最近 10 分钟 sidecar 无 `error/traceback/failed/exception`；Caddy 仅有既有 Origin Certificate OCSP stapling warning，无 upstream 错误。
- 已按用户明确授权创建一名普通、active 的试点账号并加入 `qyunslation-vue-beta`；组仍为非 superuser，当前成员数为 1。密码仅通过受保护 Authentik API 设置，未写入仓库、日志或本证据。
- 真实公网 OIDC 流程已使用该试点账号跑通：callback 302、`/api/v1/me` 200、`workbench_v2=true`、缺失 CSRF 403、带 CSRF logout 204、登出后 `/api/v1/me` 401。
- 期间修复两项真实缺口并分别提交：BFF 请求 `tenant` scope；ID token 使用 discovery issuer + 受保护本机 JWKS；Authentik roles mapping 改用 `request.user.ak_groups` 后 capability 正常返回。

## 追加真实任务验收（2026-09-30T14:43Z–14:45Z）

- 首次任务发现 sidecar 服务 PATH 缺少 `pdf2zh_next`，任务诚实返回 `blocked / translation runner unavailable`；未将阻断误报为成功。
- 备份并更新受保护 `/home/dev/pdf2zh/office.env`，增加绝对 CLI 路径后重启 `qyunslation-office.service`；sidecar health 仍为 200，服务保持 active。
- 使用同一公网 OIDC 试点会话上传真实 `page1.pdf`，完成 `preflight=ready` → `TranslationRun=succeeded` → 下载 2 个产物（首个产物 566073 bytes）；随后缺失 CSRF logout=403、匹配 CSRF logout=204、会话 `/api/v1/me=401`。

## 待人工验收

- 由管理员确认该 `qyunslation-vue-beta` 试点用户可使用，并在浏览器完成登录。
- 用该用户完成真实浏览器 OIDC callback、BFF cookie、`/api/v1/me.capabilities.workbench_v2`、logout 和跨租户拒绝检查。
- 24 小时观察作为补充证据，不再是硬门槛；仍需管理员确认浏览器视觉和跨租户拒绝界面后，进入 067g/067h 的受控 Gradio 退役决策。
