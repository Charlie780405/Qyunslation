# PLAN-067：Qyunslation Authentik → Vue `/next` 公网灰度与 Gradio 退役评估

状态：**进行中 · Vue/BFF 已完成公网灰度；按完整验收证据推进 Gradio 受控退役评估**

## 目标

在不破坏现有 Gradio 根入口、旧任务和下载能力的前提下，完成 Authentik OIDC、BFF 会话、Vue `/next` 公网灰度，并以完整自动化、真实端到端和回滚证据评估 Gradio 是否进入受控退役阶段。24 小时观察不再作为硬门槛，但不得以未验证的功能或不可回滚的卸载替代测试。

## 已冻结决策

- Vue `/next` 是正式目标 UI；Gradio 只作为迁移期回退入口。
- 登录只使用公司 SSO；不提供用户名/密码备用表单。
- 灰度使用 Authentik 试点组 `qyunslation-vue-beta`，服务端映射为 `workbench_v2` capability。
- 观察窗口作为补充证据，不再是用户确认的硬门槛；完整验收、真实任务和回滚证据为退役前置条件。
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
| 067d | 登录、回调、`/api/v1/me`、登出、CSRF 验收 | 067c | **进行中 · 真实公网 OIDC/API 会话通过；人工浏览器视觉与跨租户验收待完成** |
| 067e | Caddy 灰度路由 | 067d | **已部署 · Vue/BFF 公网探针通过；进入观察期** |
| 067f | 试点组与运行观察 | 067e | **进行中 · 试点账号与公网会话已通过，补充真实任务/浏览器证据** |
| 067g | Gradio 退役与冗余模块审计 | 067f | **进行中 · 只读审计完成，按完整验收决定受控退役** |
| 067h | 交付证据、回滚与最终验收 | 067a–067g | 待执行 |

## 附件适用性

`qyunslation-ui-ux-plan.md` 是 UI/UX 参考提案，不是当前仓库的绑定实施指令。采纳其文档对照、渐进式高级设置、检查器、术语治理、响应式和可访问性原则；覆盖其用户名/密码登录、旧颜色令牌、32px 点击区域、Gradio CSS 优先和任意 `ui=v2` 查询参数建议。PLAN-066 的 SSO、视觉令牌、44px 触控目标、Manifest/revision/QA 审计模型和 Vue 迁移边界优先。

## 当前缺口与观察门槛

- 仍需人工浏览器视觉、跨租户界面和至少一个真实 Vue 翻译任务的操作证据。
- `office-archive-watch.service` 曾因受保护虚拟环境缺少 `minio` crash-loop；已补齐锁定依赖并恢复 active，仍不得视为冗余模块。
- 在根入口切换前必须完成旧任务/下载、PDF 归档 watcher 和 Caddy 回滚验证；服务停用与删除仍需单独证据，不与路由切换混为一步。

## 完成与回滚原则

- 每个子计划先做专项验证，再精确提交、推送并记录 WT 证据。
- 任何认证、租户隔离、Gradio 根入口、旧下载或任务完整性回归，停止后续切换并恢复最近一次 Caddy 配置备份。
- 不回滚数据库迁移、不删除任务数据、不重复执行运行中的翻译任务。
