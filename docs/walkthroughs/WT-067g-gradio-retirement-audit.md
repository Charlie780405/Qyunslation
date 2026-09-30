# WT-067g：Gradio 退役与冗余模块只读审计证据

对应计划：[PLAN-067g](../plans/PLAN-067-workbench-public-cutover/PLAN-067g-gradio-retirement-audit.md)

## 现场证据（2026-09-30T14:19Z）

- `pdf2zh.service` active，监听 `127.0.0.1:7860`；公网根路径仍由它提供 Gradio 登录页。
- `qyunslation-office.service` active，监听 `127.0.0.1:8010`；Vue/BFF 公网灰度依赖它。
- `pdf2zh-archive-watch.service` active，`NRestarts=0`；归档职责仍在运行。
- `office-archive-watch.service` 在基线时因 `ModuleNotFoundError: No module named 'minio'` crash-loop，明确不是安全的卸载证据。
- Authentik server/worker/PG、q yunsgen Caddy 均为当前 OIDC/TLS 路径的运行依赖。

## 追加证据（2026-09-30T14:42Z–14:48Z）

- 全量仓库回归：`1010 passed, 6 skipped, 8 warnings`；前端 `type-check` 与 `build` 通过。
- 公网探针：`/next/login=200`、`/api/v1/health=200`、未授权 `/api/v1/me=401`、`/auth/login?format=json=200`、Vue 静态 chunk=200；根路径仍为 Gradio 登录页。
- 真实试点账号登录、`workbench_v2` capability、CSRF 拒绝/接受、登出撤销和预检创建均通过。
- 第一次真实 PDF 任务因 sidecar 服务 PATH 缺少 `pdf2zh_next` 被阻断，未伪造成功；已增加绝对 CLI 配置并重启 sidecar。
- 修复后真实 `page1.pdf` 完整通过：公网 OIDC 登录、预检 ready、TranslationRun succeeded、2 个产物下载（首个 566073 bytes）、CSRF logout 和会话撤销均通过。
- 归档/runner 相关回归：`23 passed`（归档、PDF runner、TranslationRun）；全量回归仍为 `1010 passed, 6 skipped`。
- 已将 `minio>=7.2.15` 纳入 `pyproject.toml/uv.lock`，受保护 `.venv` 安装解析为 `7.2.20`；MinIO health=200，watcher 重启后 `active/running`、`NRestarts=0`，日志确认历史 Office 产物归档与向量索引完成。

## 结论

本切片没有执行 stop、disable、uninstall 或删除。真实 TranslationRun 和归档 watcher 已通过，但人工浏览器视觉证据、根入口切换和回滚演练仍需在 067h 逐步完成；归档 watcher 继续保留。

067h 已完成后续动作：根路径已切到 Vue，旧域名只做兼容重定向，Caddy 不再代理 7860；`pdf2zh.service` 已 `disable --now`，但包、配置、历史产物和回滚备份仍保留。

## 缺口传递到后续

- 067h 必须提供完整自动化回归、真实 Vue 翻译闭环、Caddy 回滚演练和旧产物下载证据；24 小时指标作为补充而非硬门槛。
- 归档 watcher 依赖修复已独立完成；后续仍不得把归档职责并入 Gradio 卸载动作。
