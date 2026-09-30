# PLAN-067e：Caddy Vue 灰度路由

状态：**已部署 · 2026-09-30T13:52Z 起进入观察期**

## 目标

在不改变 `translate.qyunsgen.com/` Gradio 根入口的前提下，将 Vue/BFF 的有限路径接入 sidecar `127.0.0.1:8010`，为真实 OIDC 浏览器验收提供公网入口。

## 路由契约

| 路径 | 上游 | 约束 |
|---|---|---|
| `/next`、`/next/*` | `127.0.0.1:8010` | SPA 页面，不创建新任务 |
| `/app-assets/*` | `127.0.0.1:8010` | immutable 缓存 |
| `/auth`、`/auth/*` | `127.0.0.1:8010` | `no-store`，BFF 会话和回调 |
| `/api/v1`、`/api/v1/*` | `127.0.0.1:8010` | 受认证和租户隔离保护 |
| 其它路径（包括 `/`） | `127.0.0.1:7860` | 保留 Gradio 回退入口 |

Gradio SSE matcher 保持在 Vue 路由之前的独立分支；Vue 路由只匹配上述明确前缀，不使用 catch-all 覆盖旧入口。

## 生产变更

- qyunsgen feature commit：`8479bdce`。
- qyunsgen main merge/push：`eb15b57d`。
- Caddy 配置校验通过后，因单文件 bind mount inode 保持旧内容，按部署规范仅重建 `qyunsgen-caddy` 容器；未重启 app、数据库、Redis、MinIO 或 Qyunslation sidecar。
- 回滚点：恢复 `fd26ce62` 对应 Caddy 配置并重建 `qyunsgen-caddy`；不回滚数据库和 TranslationRun 数据。

## 观察期要求

从 `2026-09-30T13:52Z` 起记录登录失败、`/api/v1` 5xx、sidecar 错误、Caddy 连接错误和 Gradio 根入口可用性。未完成真实试点账号浏览器验收及至少一个发布窗口前，不得把 Gradio 判定为可卸载。
