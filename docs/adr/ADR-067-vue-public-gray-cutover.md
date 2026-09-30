# ADR-067：Vue `/next` 公网灰度与 Gradio 回退

状态：已接受，按 PLAN-067 分阶段实施。

## 背景

PLAN-066 已在 sidecar 中提供 Vue 工作台、BFF 会话和 TranslationRun，但公网根入口仍是 Gradio。直接替换根路径或卸载 Gradio 会同时放大认证、任务执行、下载和回滚风险。

## 决策

先配置并验证 Authentik OIDC 与 BFF，再由 Caddy 将指定 Vue 路径灰度到 sidecar；根路径继续保持 Gradio。Vue 首阶段只向 Authentik `qyunslation-vue-beta` 试点组开放。观察一个工作日/24 小时后，依据真实登录、任务、下载和错误指标决定是否扩大灰度。Gradio 退役必须是单独的后续变更，不得与首次路由切换或数据库迁移绑定。

## 影响

- 需要维护 `/home/dev/qyunsgen` 中的独立 Caddy 配置变更和回滚备份。
- 需要在受保护环境注入 client ID 与 BFF session key。
- 旧 Gradio、PDF 服务、归档和下载模块在证据证明不再使用前继续保留。
- 任何安全或数据完整性回归均可通过移除灰度路由回退，不删除新任务数据。
