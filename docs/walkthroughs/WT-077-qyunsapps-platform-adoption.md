# WT-077：接入 QyunsApps 平台控制面

> 对应计划：[PLAN-077](../plans/PLAN-077-qyunsapps-platform-adoption/PLAN-077-qyunsapps-platform-adoption.md)
> 日期：2026-10-18 · 分支：`feat/PLAN-077-qyunsapps-platform-adoption`（worktree，未合并 main，未部署）
> 状态：**T1、T2 已实现并验证；T3、T4、T5 的准备件已写好；T6、T7 与所有生产写操作待用户执行**

## 1. 执行摘要

- 翻译业务、模型 profile、任务 schema、数据库 schema 均未改动；主工作区未提交的 `.env.example` 与 `gateway/provider.py` 改动没有被复制或提交（本分支只在 worktree 内）。
- Vue/BFF 侧新增最小接入：令牌、`<qyuns-appbar>`、平台退出链、AppShell 退出按钮追加 Authentik end-session。
- 边缘/身份合同写成 MD + JSON + pytest，并与 QyunsApps 的站点与蓝图对账（做过负向对照：改一个超时即失败）。
- 5433 暴露面：只读证据已取，变更已备好但**未执行**；发现一个需要用户尽快确认的风险（见 §5）。

## 2. 变更明细

| 任务 | 内容 | 文件 |
| --- | --- | --- |
| T1 | 合同 | `docs/contracts/qyunsapps-edge-identity.md`、`tests/contracts/qyunsapps-contract.json`、`tests/contracts/test_qyunsapps_contract.py` |
| T2 | 令牌与顶栏（QyunsApps 生成，带 sha 头和校验和） | `frontend/src/next/vendor/{tokens.css,tw3-preset.cjs,qyunsapps-vendored.json}`、`frontend/public/qyuns-appbar.js` |
| T2 | 退出链与顶栏挂载 | `frontend/src/next/qyuns/{index,logout,appbar-mount}.js`、`qyuns.css` |
| T2 | 少量接线 | `frontend/src/main.js`（+1 import、+1 条件分支）、`frontend/src/next/components/AppShell.vue`（退出后跳 end-session）、`frontend/tailwind.config.js`（加 preset） |
| T2 | 测试 | `frontend/src/next/__tests__/qyuns.test.js`（21 项） |
| T2 | 构建产物（单独的 `build:` 提交） | `qyunslation/static/app/*` |
| T3 | 备好未执行 | `docs/runbooks/pg-loopback-binding.md` |
| T4 | 决策包 | `docs/assessments/object-storage-ownership.md` |
| T5 | 归属说明 | `deploy/authentik/blueprints/README.md`（旧蓝图标为迁移基线，未删除、未改内容） |

BFF（`qyunslation/auth/bff.py`）**没有改**：`POST /auth/logout` 仍校验 CSRF 并撤销 `WebSession`，前端先调它再跳转。

## 3. 验证结果

| 项 | 结果 |
| --- | --- |
| 前端 vitest | 6 个文件 45 项全过（新增 21 项：白名单、`next` 拒绝、CSRF 读取、超时回退、顶栏挂载条件） |
| pytest（`uv run --frozen`） | `tests/auth` + `tests/contracts` 共 9 项全过 |
| 合同负向对照 | 把 edge 的 `read_timeout 120s` 改成 `20s` → 边缘对账测试失败 |
| `sync-vendored.sh --check`（qyunslation） | 4 个文件全部一致 |
| 浏览器（QyunsApps `tests/adopters/qyunslation-qyuns-browser.mjs`，Chromium + WebKit） | 50 项全过：顶栏 48px 且在最上方；外壳在顶栏之下；整页没有因 100vh 多出滚动；`--qy-primary` 已映射品牌色；顶栏 axe 0 serious；手机宽度无横向滚动、触控目标 ≥44px；退出按钮先 `POST /auth/logout` 且带 CSRF，再到 end-session；退出链合法 `next` 正常跳转且不先请求 `/me`；会话过期时无 `next` 也到 end-session；4 种恶意 `next` 全部被拒、没有 POST；未登录不挂顶栏 |

浏览器检查在 Playwright 里拦截 `https://translate.qyunsgen.com/**` 并用本地 `static/app` 与假接口应答，没有向任何真实服务发请求。

## 4. 回归确认

- 业务代码、schema、模型配置零改动；`git diff main --stat` 里除上表文件外只有 `static/app` 构建产物。
- 没有读取 `.env`；没有对 Caddy、Authentik、systemd、Compose、数据库做任何写操作。

## 5. 已知限制与需要你注意的事

1. **PG 绑定（T3）**：`qyunslation-plan034c-pg` 发布在 `0.0.0.0:5433`，主机有公网网卡；防火墙我读不到（需要 sudo）。当前连接全部来自本机 qyunslation 服务，没有远程消费者。compose 里口令默认值是公开的 `qyunslation_dev_only`，我无法确认生产是否覆盖。建议尽快：确认防火墙，并按 `docs/runbooks/pg-loopback-binding.md` 收口。这是本计划里最值得优先处理的一项。
2. 数据库有排序规则版本告警（建库 2.41、系统 2.36），未处理，登记为遗留。
3. `static/app` 是提交进 git 的构建产物；合并前需在最终源码上再构建一次，确保与源码一致。
4. 顶栏仅在 `translate.qyunsgen.com` 挂载；本地/其他主机不显示，这是有意的。
5. Authentik 2025.10 的 end-session 不支持回跳，最终停在"已退出"页。

## 6. 后续计划步骤

| 步骤 | 谁 | 前置 |
| --- | --- | --- |
| 审阅并合并本分支到 qyunslation `main` | 用户 | 主工作区未提交的改动先处理，避免与本分支冲突 |
| 重新 `vite build`、提交 `static/app`、按既有 systemd/Vue 发布流程上线（T7） | 用户确认 | 合并后 |
| 执行 PG loopback 收口（T3） | 用户确认窗口 | 备份；先确认防火墙与口令 |
| 补对象存储 5 项证据（T4），再决定是否迁移 | 用户 + 后续计划 | — |
| QyunsApps 侧 apply `qyunslation-oidc` 蓝图并做授权码往返（T5） | 用户执行 | QyunsApps WT-001b §6.1 |
| Authentik runtime 迁出（T6） | 需单独批准 | QyunsApps PLAN-002e；不与 T3/Caddy 同窗 |
| 运行 QyunsApps 002g 只读 SSO/logout/edge smoke | — | 上线后 |
