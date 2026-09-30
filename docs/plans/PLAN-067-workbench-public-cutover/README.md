# PLAN-067：Qyunslation Authentik → Vue `/next` 公网灰度与 Gradio 退役评估

状态：**进行中 · 067a 运行时基线与契约已冻结；尚未执行 Authentik/Caddy 生产切换**

## 目标

在不破坏现有 Gradio 根入口、旧任务和下载能力的前提下，完成 Authentik OIDC、BFF 会话、Vue `/next` 公网灰度，并在一个工作日/24 小时观察窗口后，以证据评估 Gradio 是否进入退役阶段。

## 已冻结决策

- Vue `/next` 是正式目标 UI；Gradio 只作为迁移期回退入口。
- 登录只使用公司 SSO；不提供用户名/密码备用表单。
- 灰度使用 Authentik 试点组 `qyunslation-vue-beta`，服务端映射为 `workbench_v2` capability。
- 观察窗口最短为一个工作日/24 小时。
- BFF 唯一回调为 `https://translate.qyunsgen.com/auth/callback`。
- 浏览器只持有 HttpOnly BFF 会话，不持有 OIDC access/refresh token。
- `/next`、`/app-assets`、`/auth`、`/api/v1` 通过 Caddy 灰度到 `:8010`；根路径继续到 Gradio `:7860`。
- 不直接卸载 Gradio、`pdf2zh.service`、归档 watcher、受保护下载或旧复核资源。
- Caddy 变更属于 `/home/dev/qyunsgen` 的独立生产配置变更，必须单独备份、审查、提交或记录部署工件。

## 子计划与依赖

| 子计划 | 内容 | 依赖 | 当前状态 |
|---|---|---|---|
| 067a | 运行时基线、设计输入与切换契约 | 无 | **已完成** |
| 067b | Authentik 应用、DNS、回调契约 | 067a | **已完成 · provider、Caddy、公共 DNS/JWKS 门禁通过** |
| 067c | 密钥注入与 sidecar 会话配置 | 067b | **已完成 · 生产 apply、0600 备份、sidecar 重启和健康验证通过** |
| 067d | 登录、回调、`/api/v1/me`、登出、CSRF 验收 | 067c | **进行中 · 本机预检通过；真实浏览器验收随 067e 灰度完成** |
| 067e | Caddy 灰度路由 | 067d | **已部署 · Vue/BFF 公网探针通过；进入观察期** |
| 067f | 试点组与 24 小时观察 | 067e | **进行中 · 已建立基线，等待真实试点账号与观察窗口** |
| 067g | Gradio 退役与冗余模块审计 | 067f | 待执行 |
| 067h | 交付证据、回滚与最终验收 | 067a–067g | 待执行 |

## 附件适用性

`qyunslation-ui-ux-plan.md` 是 UI/UX 参考提案，不是当前仓库的绑定实施指令。采纳其文档对照、渐进式高级设置、检查器、术语治理、响应式和可访问性原则；覆盖其用户名/密码登录、旧颜色令牌、32px 点击区域、Gradio CSS 优先和任意 `ui=v2` 查询参数建议。PLAN-066 的 SSO、视觉令牌、44px 触控目标、Manifest/revision/QA 审计模型和 Vue 迁移边界优先。

## 当前硬阻断

- `/home/dev/pdf2zh/office.env` 尚缺 `QYUNSLATION_OIDC_CLIENT_ID` 与 `QYUNSLATION_SESSION_KEY`。
- `auth.qyunsgen.com` 的 Cloudflare 权威与公共递归已返回 A 记录，但生产主机上游 `108.61.10.10` 仍返回 NXDOMAIN；必须等其负缓存刷新或由主机运维切换到可用的受控 resolver。
- 生产 Caddy 尚无 Authentik 站点及 `/next`、`/app-assets`、`/auth`、`/api/v1` 路由。
- PLAN-054 的旧脚本仍使用 `/oauth2/callback`，必须与 BFF `/auth/callback` 对齐后才能切换。
- `office-archive-watch.service` 因缺少 `minio` Python 依赖持续自动重启；它是故障服务，不是已证实的冗余服务。

## 完成与回滚原则

- 每个子计划先做专项验证，再精确提交、推送并记录 WT 证据。
- 任何认证、租户隔离、Gradio 根入口、旧下载或任务完整性回归，停止后续切换并恢复最近一次 Caddy 配置备份。
- 不回滚数据库迁移、不删除任务数据、不重复执行运行中的翻译任务。
