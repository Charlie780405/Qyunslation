# PLAN-067h：最终验收、Vue 正式入口与 Gradio 可逆退役

状态：**已完成**

## 目标

在不删除翻译包、历史产物、归档职责或数据库数据的前提下，将公网正式入口切到 Vue，验证认证、API、构建、任务执行和回滚，并受控停用 Gradio WebUI。

## 执行顺序

1. 评估 UI 参考并把 Beautiful UI、beUI、Rare UI、Transitions.dev、shadcn/ui 的可复用原则写入设计系统；不引入 React 运行时或第三方注册表。
2. 对 Caddy 配置做带时间戳备份，先验证新根路径和旧入口，再提交、推送并重建 Caddy。
3. 做回滚演练：临时恢复切换前 Caddy，确认根路径回到 Gradio，再恢复新配置并确认 Vue 正常。
4. 执行全仓库和前端测试；复核 Authentik、BFF、API、归档 watcher 和 sidecar 状态。
5. 将未知路径和 `office.qyunsgen.com` 重定向到 Vue，移除 Caddy 对 `127.0.0.1:7860` 的依赖。
6. `systemctl --user disable --now pdf2zh.service`，不删除 unit、Python 包、补丁、配置、历史产物或数据库。
7. 停用后再次验证根路径、Vue、健康检查、未授权响应、旧域名重定向、归档 watcher 和 sidecar。

## 完成门槛

- [x] Caddy 配置有效，源文件与容器内文件 SHA 一致。
- [x] 根路径 `302 → /next/`，`/next/login=200`，`/api/v1/health=200`，匿名 `/api/v1/me=401`。
- [x] Authentik provider、DNS、JWKS、回调、CSRF 和 beta group 门禁通过。
- [x] 真实 PDF 已完成公网 OIDC → preflight ready → TranslationRun succeeded → 2 个产物下载；失败路径曾诚实返回 blocked。
- [x] 全仓库 `1010 passed, 6 skipped, 8 warnings`；前端 type-check/build 通过。
- [x] 回滚演练成功：旧 Caddy 根路径 200/Gradio，恢复新配置后根路径再次 302/Vue。
- [x] `pdf2zh.service` 为 disabled/inactive、7860 端口关闭；`qyunslation-office.service`、两个 archive watcher 均 active 且 `NRestarts=0`。
- [x] 不存在 Caddy → 7860 的公网 upstream；`office.qyunsgen.com` 仅作旧链接兼容重定向。

## 保留项与回滚

- 保留 Gradio Python 包、`/home/dev/pdf2zh` 配置、所有 patch 脚本、历史产物和归档 watcher；本次“卸载”是服务退役，不是不可恢复的物理删除。
- 回滚时先恢复备份的 Caddy 配置并重建 Caddy，再 `systemctl --user enable --now pdf2zh.service`；不回滚数据库迁移、不重复执行正在运行的 TranslationRun。
- 人工浏览器视觉验收受当前环境无 Chromium/浏览器会话限制，未伪造为通过；自动化 API、构建、可访问性规则和真实任务证据已留档。
