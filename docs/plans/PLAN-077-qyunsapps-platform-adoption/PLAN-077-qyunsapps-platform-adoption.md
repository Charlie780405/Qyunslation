# PLAN-077 — Qyunslation 接入 QyunsApps 平台控制面

> 状态：**T1、T2 已实现并合并；T3 的 PG 端口收口已合并（`6ecd306`），口令核对待用户；T4/T5 准备件已备好；T6/T7 与生产写操作待用户确认（2026-10-18，见 WT-077；后续事项归入 PLAN-079 §6.F）** · 创建 2026-10-18 · 上游：`/home/dev/QyunsApps/docs/plans/PLAN-002-platform-ownership/PLAN-002-platform-ownership.md`、PLAN-001g · WT：`docs/walkthroughs/WT-077-qyunsapps-platform-adoption.md`

## 1. 目标

- Qyunslation 保留翻译服务、Vue/BFF、业务 PostgreSQL/Alembic、SQLite 归档、watcher 和对象数据的所有权。
- 将 `translate`/`office` 路由、OIDC 客户端行为、健康端点和长任务超时固化为合同，由 QyunsApps 持有唯一生产 Caddy 与 Authentik desired state。
- 接入 QyunsApps 生成令牌、`<qyuns-appbar>` 和 RP logout，不改变翻译业务页面或任务语义。
- 只读核查并收口业务 PostgreSQL `0.0.0.0:5433` 暴露面；形成对象存储从 qyunsgen MinIO 解耦的决策包，但本计划不迁对象数据。
- 在用户单独批准 QyunsApps PLAN-002e 时，安全迁出 Authentik runtime；默认不阻塞 Portal MVP。

## 2. 前置条件

- QyunsApps PLAN-002a/002d 与 PLAN-001d/e 完成；Caddy 生产切换按 PLAN-002c 独立执行。
- 当前主工作区有未提交改动；所有 PLAN-077 工作仅在独立 worktree，禁止复制或覆盖主工作区文件。
- 开始前阅读 PLAN-076 WT/缺口和 PLAN-067 Auth/Caddy 基线，确保不破坏现有 Vue/BFF/OIDC。
- 生产 `.env`、systemd、Compose、Caddy、Authentik、数据库绑定由用户逐项确认。

## 3. Out of Scope

- 翻译提示词、模型 profile、术语、QA、任务 schema 或业务数据迁移。
- 合并 qyunslation PG 与 Authentik PG/其他应用 PG。
- 在本计划迁移 SQLite 归档或 MinIO 对象数据。
- 与 Caddy 首切同窗迁移 Authentik runtime。
- 删除 `deploy/authentik`、旧卷、备份或 qyunsgen MinIO bucket。

## 4. 关键决策

- QyunsApps 是共享 Caddy 和 Authentik desired-state SSOT；本仓保留客户端合同、应用代码和迁出前恢复副本，不双向编辑蓝图/站点配置。
- UI 生成文件带 QyunsApps sha，由 drift check 验证；Qyunslation 只维护最小 Vue custom-element 挂载和 token 映射。
- PG 绑定加固先证明真实消费者；目标是容器内网或 loopback，不以“可能有防火墙”为长期例外。
- 对象存储跨仓依赖先审计 bucket/prefix/恢复/key Owner，再另立迁移 ADR/PLAN；本计划没有数据搬运权限。
- Authentik runtime 迁出使用同版本/同域名/同数据，升级另立计划；旧栈保留 2–4 周可回滚。

## 5. 任务

### T1 冻结边缘与 OIDC 客户端合同

- **内容**：声明 `/next`、`/app-assets`、`/auth`、`/api/v1`、root/office redirect、`:8010`、health、timeout、安全头、OIDC callback/logout/claims；与 QyunsApps registry/blueprint 对账。
- **验收**：迁入 QyunsApps 的站点/蓝图与 PLAN-067 现网行为等价；无 secret/PII；旧配置标为迁移基线而非继续编辑 SSOT。
- **验证**：BFF/API tests、Caddy contract fixture、QyunsApps 002a/002b/002d checks。
- **依赖**：QyunsApps 002a/002d。**文件**：`docs/contracts/qyunsapps-edge-identity.md`、合同 fixture/tests（最多 3 文件）。

### T2 接入令牌、顶栏与退出

- **内容**：同步生成 token/appbar，配置 Vue custom element，在 AppShell 最小挂载；保留 CSRF 与 `WebSession` 撤销后追加 Authentik end-session，`next` 主机白名单。
- **验收**：`/next` 桌面/平板/手机无回归；触控目标 ≥44px；POST logout 仍校验 CSRF；恶意 `next` 被拒；退出后保护页要求登录。
- **验证**：前端 build/unit、BFF auth tests、设备矩阵/axe、`sync-vendored.sh --check`、浏览器 logout E2E。
- **依赖**：PLAN-001d/e、T1。**文件**：生成资源、AppShell/next.css 少量接线、BFF logout/tests；分切片每次不超过 5 文件。

### T3 收口 PostgreSQL 暴露面

- **内容**：只读确认 `5433` 的本机/远程消费者、宿主防火墙和 deploy_gate；在用户批准后把 Compose publish 收口到 loopback 或移除宿主 publish，更新健康/迁移/备份命令并演练回滚。
- **验收**：远程业务流无意外依赖；PG 不再无说明绑定所有接口；Alembic 和 sidecar 正常；其他数据库/应用不被重启。
- **验证**：切换前后 `ss`/Compose config、Alembic current、sidecar health、备份/隔离恢复和真实消费者 smoke。
- **依赖**：QyunsApps 002f、用户确认。**文件**：`docker-compose.plan034c.yml`、相关 runbook/verify、WT；不得读取生产 `.env`。

### T4 形成对象存储解耦决策包

- **内容**：记录 qyunsgen MinIO 中 qyunslation bucket/prefix、消费者、容量级别、加密 key Owner、备份/恢复与停机要求；比较本仓独立 MinIO、共享存储独立账号/bucket、保持现状。
- **验收**：不下载、不复制、不删除对象，不读取 access key；给出推荐方案、迁移门禁和独立回滚边界。
- **验证**：只读配置/接口/备份证据对账；敏感扫描；QyunsApps 002f evidence manifest。
- **依赖**：QyunsApps 002f。**文件**：`docs/assessments/object-storage-ownership.md`、PLAN/WT 缺口登记。

### T5 迁出 Authentik desired state

- **内容**：确认 QyunsApps 002d 已等价接管 qyunslation provider/flow 蓝图；本仓旧蓝图在观察期内保留恢复副本，部署脚本停止把它当作活动 SSOT。
- **验收**：二次 apply 幂等；qyunslation SSO 无回归；本仓没有另一条会写同一对象的日常流程。
- **验证**：QyunsApps blueprint diff/apply、qyunslation 授权码往返与 logout；仓库引用扫描。
- **依赖**：QyunsApps 002d、用户执行 Authentik apply。**文件**：`deploy/authentik/blueprints/` 归属说明、相关脚本/文档（仅在等价验证后改）。

### T6 Authentik runtime 迁出（可选，高风险）

- **内容**：作为 QyunsApps 002e 的 qyunslation 对应切片，提供旧栈备份/停止/恢复与观察证据；不在本仓构建第二个新栈。
- **验收**：同版本恢复演练通过；新 runtime health/SSO/logout 通过；旧 Compose/卷保留 2–4 周；qyunslation 发布不再管理 IdP。
- **验证**：以 QyunsApps 002e runbook/evidence 为主，本仓验证旧栈可恢复和应用客户端无变化。
- **依赖**：T5、QyunsApps 002e 单独批准；不得与 T3/Caddy 切换同窗。**文件**：本仓 Authentik 部署文档、WT；首次切换不删除文件/卷。

### T7 灰度发布与证据收口

- **内容**：按 qyunslation 既有 systemd/Vue 发布流程上线 T2；T3、T5、T6 各用独立窗口；运行 QyunsApps 002g 只读 SSO/logout/edge smoke。
- **验收**：翻译任务、预检、恢复、归档 watcher、SSO、顶栏、退出、health 无回归；模型/gateway 主工作区改动未混入。
- **验证**：现有专项 verify、sidecar health、浏览器矩阵、QyunsApps evidence manifest。
- **依赖**：对应任务完成、用户确认。**文件**：`docs/walkthroughs/WT-077-qyunsapps-platform-adoption.md`。

## 6. 验证清单

- [ ] 主工作区用户改动未被复制、覆盖或提交。
- [ ] 无业务 schema/数据/翻译质量行为变化。
- [ ] Caddy/Auth desired state 只有 QyunsApps 一个活动 SSOT。
- [ ] UI/token/appbar/logout 测试和漂移门禁通过。
- [ ] PG 非内部绑定有证据收口且可回滚。
- [ ] 对象存储只完成决策包，没有数据移动。
- [ ] Authentik runtime 迁出与 Caddy/PG 变更分窗，旧栈可恢复。

## 7. 回滚预案

UI/Logout 回滚到旧 release；PG 绑定按执行前 Compose 备份恢复并只重启本仓 PG/sidecar；desired-state 回滚只恢复本计划创建/修改的 Authentik 对象；runtime 迁移按 QyunsApps 002e 停新启旧。对象存储没有数据变更，无需数据回滚。

## 8. 影响范围

Qyunslation Vue/BFF 最小接入、边缘/身份合同、PG 网络边界、对象存储决策文档和 Authentik 迁出协作；翻译业务代码、模型 profile、数据库 schema 与历史对象保持不变。

