# PLAN-067a：运行时基线、设计输入与切换契约冻结

状态：**已完成（文档冻结；未改变生产行为）**

## 目的

把当前生产事实、附件 UI/UX 输入、PLAN-066 约束、Authentik/BFF 回调和 Caddy 灰度边界固化为后续实施的唯一参考，避免把旧文档或推测当成生产事实。

## 生产事实

| 领域 | 当前事实 | 证据/影响 |
|---|---|---|
| 代码 | qyunslation `main` 与 `origin/main` 均为 `931461e` | 067a 开始前读取 Git 状态；本地 IDE 文件与演示目录未纳入提交 |
| 根入口 | `translate.qyunsgen.com/` 仍由 Gradio `:7860` 提供 | `/next`、`/app-assets`、`/auth`、`/api/v1` 尚未由公网 Caddy 转发 |
| sidecar | `qyunslation-office.service` 监听 `127.0.0.1:8010` | 本地 `/next/login`、`/app-assets/index.html`、`/api/v1/health` 可达 |
| PDF/Gradio | `pdf2zh.service` 监听 `127.0.0.1:7860` | 仍承担根入口、PDF 引擎、旧任务和回退路径 |
| Authentik | 本地 server/worker/PG 健康 | 本地 Authentik 不是公网 issuer；公网 DNS/Caddy 仍需确认 |
| BFF | OIDC PKCE、state/nonce、加密 token set、HttpOnly 会话、双提交 CSRF 已实现 | 缺 client ID/session key 时 `/auth/login` 返回配置错误 |
| 数据库 | PLAN-066 迁移已部署至 `066e0002` | 本子计划不执行迁移或回滚 |
| 归档 | `pdf2zh-archive-watch` 运行；`office-archive-watch` 自动重启失败 | 后者缺 `minio` 模块，不能据此判断可删除 |

## 切换契约

### Authentik/BFF

- canonical issuer：`https://auth.qyunsgen.com/application/o/qyunslation/`
- canonical redirect：`https://translate.qyunsgen.com/auth/callback`
- 浏览器只收到 BFF 随机会话 Cookie 和可读 CSRF Cookie。
- 租户、用户、角色和 `workbench_v2` capability 必须由服务端认证上下文生成。
- `return_to` 只允许同源站内路径。

### Caddy 路由

灰度时路由顺序必须为：

1. Gradio SSE 特殊处理。
2. `/next`、`/next/*` → `127.0.0.1:8010`。
3. `/app-assets/*` → `127.0.0.1:8010`。
4. `/auth`、`/auth/*` → `127.0.0.1:8010`。
5. `/api/v1`、`/api/v1/*` → `127.0.0.1:8010`。
6. 其它根路径 → `127.0.0.1:7860`。

路由必须保留原始路径；不得暴露 `/service/*`、内部工作台接口、服务器文件路径或调试 OpenAPI。

### 灰度与回滚

- Authentik 组 `qyunslation-vue-beta` 才能获得 `workbench_v2`。
- 试点组外用户继续使用 Gradio 根入口。
- 观察窗口为一个工作日/24 小时。
- 发现越权、跨租户、token 泄漏、任务重复/丢失、持续 5xx 或旧入口回归时，立即移除灰度路由；保留数据库和新任务数据。

## 附件决策记录

### 采纳

- 文档对照优先；源文只读、译文可修订。
- 默认低密度入口，高级设置渐进展开。
- 检查器按源文、译文、术语、QA、修订历史组织。
- 术语列表分页/虚拟化、详情抽屉、风险筛选和逐项高风险确认。
- 修复检查器裁切、开发者文本、左栏溢出和登录重复文案。

### 覆盖

- 登录页使用公司 SSO 单按钮，不使用用户名/密码表单。
- 颜色使用 PLAN-066 `--qy-*` 令牌，不采用附件中的另一组颜色。
- 交互控件最小 44×44px，不采用 32px。
- 新能力进入 Vue `/next`，不继续扩大 Gradio CSS 补丁。
- 使用服务端 capability，不接受任意查询参数作为生产开关。

### 暂缓

- 多语言全面验收、TBX、多人协同、移动端完整对象编辑。
- 未经设置 schema 冻结的“快速/精准”新业务模式。

## 非目标

- 不在 067a 中修改 Python、Vue、Caddy、Authentik、systemd 或数据库。
- 不安装/卸载依赖，不停止服务，不重启生产。
- 不把 `.env`、client secret、session key、数据库 URL 或日志凭据写入仓库。

## 验证

- `git status --short --branch`：仅保留已有 `.cursor/mcp.json` 与 `slide-deck/` 未跟踪项。
- 核对 `Caddyfile-production-public`、`office.env`、BFF 配置、systemd 单元和 Authentik 健康状态。
- 对后续每个子计划，必须将本文件的事实表作为前置检查，不得沿用过期的 PLAN-054 结论。
