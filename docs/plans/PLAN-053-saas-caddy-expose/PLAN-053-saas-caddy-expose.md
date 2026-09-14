# PLAN-053：SaaS 接线（Caddy 对外 /api/v1）

> 状态：**已实现**
> 日期：2026-09-13
> 依赖：PLAN-034c–h（`/api/v1` + OIDC + review 表）、PLAN-051/052（金标门已通）
> 验收门：`bash scripts/verify-plan-053.sh`
> Walkthrough：[WT-053](../../walkthroughs/WT-053-saas-caddy-expose.md)

## 一句话

把已在 sidecar `:8010` 落地的 `/api/v1`（含 `review/enqueue`）经 Caddy 挂到 `translate.qyunsgen.com`，并证明公网可达且 production OIDC 强制生效。

## 现状

| 层 | 状态 |
| --- | --- |
| FastAPI `/api/v1/*` | 已有（034） |
| review 入队（Postgres 同步写） | 已有（034g） |
| `QYUNSLATION_ENV=production` + OIDC | 已配置（office.env） |
| Caddy `translate` → `/api/v1` | **已接通** |

## 子计划

| ID | 交付 |
| --- | --- |
| [053a](./PLAN-053a-caddy-api-route.md) | Caddy `@qy_api` → `127.0.0.1:8010` + deploy 脚本 |
| [053b](./PLAN-053b-public-auth-gate.md) | 公网负向/正向门禁 + verify-053 |

## Out of Scope

- 正式公司 IdP（**[054](../PLAN-054-company-idp/)**）
- 翻译流水线自动调用 `review/enqueue`
- `/dl/*`（8765）修复
- `/service/*`、`/docs`、`/static/review.html` 公网暴露
- 050 UI

## 完成定义

- [x] 纲领 + 053a/b + README + WT-053；plans 索引与 051/052 回链
- [x] Caddy translate 块含 `/api/v1` → `:8010`；validate + reload
- [x] `verify-plan-053.sh`：静态 + 公网负向 + mint E2E 入队 → SUMMARY PASS
