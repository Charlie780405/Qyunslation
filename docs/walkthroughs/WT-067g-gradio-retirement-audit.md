# WT-067g：Gradio 退役与冗余模块只读审计证据

对应计划：[PLAN-067g](../plans/PLAN-067-workbench-public-cutover/PLAN-067g-gradio-retirement-audit.md)

## 现场证据（2026-09-30T14:19Z）

- `pdf2zh.service` active，监听 `127.0.0.1:7860`；公网根路径仍由它提供 Gradio 登录页。
- `qyunslation-office.service` active，监听 `127.0.0.1:8010`；Vue/BFF 公网灰度依赖它。
- `pdf2zh-archive-watch.service` active，`NRestarts=0`；归档职责仍在运行。
- `office-archive-watch.service` enabled 但 `NRestarts=198415`，最近日志明确为 `ModuleNotFoundError: No module named 'minio'`，不是安全的卸载证据。
- Authentik server/worker/PG、q yunsgen Caddy 均为当前 OIDC/TLS 路径的运行依赖。

## 追加证据（2026-09-30T14:42Z–14:44Z）

- 全量仓库回归：`1010 passed, 6 skipped, 8 warnings`；前端 `type-check` 与 `build` 通过。
- 公网探针：`/next/login=200`、`/api/v1/health=200`、未授权 `/api/v1/me=401`、`/auth/login?format=json=200`、Vue 静态 chunk=200；根路径仍为 Gradio 登录页。
- 真实试点账号登录、`workbench_v2` capability、CSRF 拒绝/接受、登出撤销和预检创建均通过。
- 第一次真实 PDF 任务因 sidecar 服务 PATH 缺少 `pdf2zh_next` 被阻断，未伪造成功；已增加绝对 CLI 配置并重启 sidecar，随后重新执行真实任务。

## 结论

本切片没有执行 stop、disable、uninstall 或删除。即使自动化回归通过，真实 TranslationRun 在 CLI 路径修复后仍需成功出稿和下载，之后才可进行可回滚的入口切换；`office-archive-watch` crash-loop 是待修复的可靠性缺口，必须保留并单独处理。

## 缺口传递到后续

- 067h 必须提供完整自动化回归、真实 Vue 翻译闭环、Caddy 回滚演练和旧产物下载证据；24 小时指标作为补充而非硬门槛。
- 另立归档 watcher 依赖修复切片，先补齐受保护虚拟环境的 `minio` 依赖并验证历史归档，再决定是否调整 restart 策略；不得把它并入 Gradio 卸载动作。
