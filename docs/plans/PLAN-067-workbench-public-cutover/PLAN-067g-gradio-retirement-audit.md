# PLAN-067g：Gradio 退役与冗余模块审计

状态：**进行中 · 只读审计完成，等待完整验收和受控切换证据**

## 目标

以自动化回归、真实 Vue 任务、历史下载、归档和回滚证据决定 Gradio 是否进入受控退役。24 小时观察作为补充指标，不再是硬门槛；不以“进程暂时空闲”或“服务故障”作为卸载依据。

## 当前依赖判定

| 组件 | 当前证据 | 判定 |
|---|---|---|
| `pdf2zh.service` / `:7860` | `translate.qyunsgen.com/` 根入口、旧任务和 Gradio SSE 仍指向它 | 不得卸载；至少保留至正式切换与回滚窗口结束 |
| `qyunslation-office.service` / `:8010` | Vue `/next`、BFF `/auth`、`/api/v1` 和 Office/图片路径依赖它 | 不得卸载 |
| `pdf2zh-archive-watch.service` | active，监听 PDF 产物并写 MinIO/SQLite；历史归档脚本和验收依赖它 | 不得卸载 |
| `office-archive-watch.service` | 已补齐 `minio==7.2.20`，重启后 active/running，`NRestarts=0`；MinIO health=200，日志出现 office 归档和向量索引完成 | 不是冗余；继续保留 |
| Authentik server/worker/PG | OIDC issuer、BFF callback 和试点登录依赖 | 不得卸载 |
| qyunsgen Caddy | 公网 TLS、Auth、Vue 灰度和 Gradio 根入口依赖 | 不得卸载 |
| 旧下载、`review.html`/PWA、patch 脚本及历史产物 | 仍被旧任务、支持和回滚流程引用 | 本阶段保留 |
| Hermes、literature、Targets 等其它服务 | 属于其它产品/工作流，未发现与 Qyunslation 灰度的安全替代关系 | 不纳入本计划卸载 |

## 退役前置门槛

1. 自动化认证、租户隔离、预检、TranslationRun、下载、前端构建和无障碍/安全测试通过。
2. Vue 真实试点完成上传/预检/翻译/下载；旧任务仍可查询和下载。
3. Gradio 回滚入口和 Caddy 上一个配置提交完成演练；切换与服务停用分步执行。
4. `office-archive-watch` 的 MinIO 依赖问题已修复并验证历史归档；不能用卸载掩盖 archive 职责。
5. 先将根入口切换到 `/legacy` 并保留服务和数据，完成健康检查后才可评估停用；不删除数据库、产物、归档和脚本。

## 新增验收发现

- 仓库全量回归已通过（`1010 passed, 6 skipped`），前端 type-check/build 和公网 Authentik/Caddy 探针通过。
- 首次真实公网 TranslationRun 暴露运行时缺口：sidecar 的 `PATH` 不包含 `pdf2zh_next`，任务被诚实标记为 `blocked / translation runner unavailable`；该结果证明正式导出门禁有效，但不能作为成功验收。
- 已在受保护的 `/home/dev/pdf2zh/office.env` 增加绝对 CLI 路径并重启 sidecar；配置备份为 `office.env.plan067e.runner.*.bak`。正在重新执行真实 PDF 闭环，成功前禁止 Gradio 退役。
- 重新执行已完成：真实 `page1.pdf` 通过公网 OIDC 试点会话完成上传、预检、TranslationRun 成功和 2 个产物下载；CSRF logout/会话撤销也通过。
- 归档 watcher 修复已完成：`minio>=7.2.15` 已写入 `pyproject.toml/uv.lock`，受保护 `.venv` 实际安装 `7.2.20`；MinIO health=200，watcher 重启后 `active/running`、`NRestarts=0`，日志确认归档和向量索引完成。
