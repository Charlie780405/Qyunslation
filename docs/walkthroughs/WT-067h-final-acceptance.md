# WT-067h：Vue 正式入口与 Gradio 可逆退役证据

对应计划：[PLAN-067h](../plans/PLAN-067-workbench-public-cutover/PLAN-067h-final-acceptance.md)

## Git 与部署

- qyunslation：`151d851` 及其后本切片文档提交，工作区仅保留既有用户未跟踪目录 `.cursor/mcp.json`、`slide-deck/`、`var/`。
- qyunsgen：`3cefad3f` 完成根路径切 Vue/保留旧入口；`82a9f972` 移除 Caddy 对 7860 的依赖并将旧域名改为 Vue 重定向；两次均已 push `origin/main` 并重建 Caddy。
- 退役前 Caddy 备份保存在 `/home/dev/qyunsgen-caddy-backups/`，未进入 Git。

## 公网与服务探针

| 探针 | 结果 |
|---|---|
| `https://translate.qyunsgen.com/` | `302`，`Location: /next/` |
| `/next/login` | `200` |
| `/api/v1/health` | `200` |
| 未授权 `/api/v1/me` | `401` |
| `/auth/login?format=json` | `200` |
| `https://office.qyunsgen.com/` | `302` 到 Vue |
| `127.0.0.1:7860` | 退役后端口关闭 |

`bash scripts/verify-plan-067b.sh` 在退役后再次通过，`fail=0 blocked=0`。

## 自动化和真实任务

- 全仓库：`1010 passed, 6 skipped, 8 warnings`。
- 前端：`npm --prefix frontend run type-check` 和 `npm --prefix frontend run build` 通过；构建仅保留既有 chunk size warning。
- 真实任务：公网 OIDC 试点会话完成 preflight ready、TranslationRun succeeded、2 个产物下载（首个 566073 bytes），随后 CSRF logout 和会话撤销通过。
- 运行时：补齐 `minio==7.2.20` 后 `office-archive-watch.service` active/running，`NRestarts=0`；PDF/Office archive watcher 均保留。

## 回滚演练

1. 临时使用切换前 Caddy 备份并强制重建 Caddy。
2. `translate.qyunsgen.com/` 返回 Gradio 登录页 200。
3. 恢复正式配置并再次强制重建 Caddy。
4. 根路径恢复 302 到 `/next/`，Vue、健康检查和旧域名重定向均正常。

## 退役判定

`pdf2zh.service` 已执行 `disable --now`，状态为 `disabled/inactive`，7860 端口关闭。没有删除 Python 包、配置、补丁、数据库、历史产物或 archive watcher，因此仍可按上述备份恢复。其它服务没有发现可安全卸载的冗余项：sidecar、Authentik、Caddy、MinIO、两个 archive watcher 都仍是正式链路依赖。

人工浏览器视觉验收未在当前无 Chromium 的执行环境中伪造通过；设计输入和 UI 质量门禁已加入 [Qyunslation Design System v2](../design-system/qyunslation-v2-ui-reference-addendum.md)，后续有浏览器环境时只需补视觉快照，不改变生产路由或认证契约。
