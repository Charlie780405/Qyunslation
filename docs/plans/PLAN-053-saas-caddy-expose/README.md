# PLAN-053：SaaS 接线（Caddy 对外 /api/v1）

> 状态：**已实现**
> 类型：网关暴露 + 公网鉴权门禁（不写新 API）
> 依赖：PLAN-034c–h、PLAN-051/052
> 验收：`bash scripts/verify-plan-053.sh`

## 文件索引

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 纲领 | [PLAN-053-saas-caddy-expose.md](./PLAN-053-saas-caddy-expose.md) | 目标与 Out of Scope |
| 053a | [PLAN-053a-caddy-api-route.md](./PLAN-053a-caddy-api-route.md) | Caddy 路由 + deploy |
| 053b | [PLAN-053b-public-auth-gate.md](./PLAN-053b-public-auth-gate.md) | 公网门禁 |

## 验收

```bash
bash scripts/deploy-plan-053-api-expose.sh
bash scripts/verify-plan-053.sh
```

Walkthrough：[WT-053-saas-caddy-expose.md](../../walkthroughs/WT-053-saas-caddy-expose.md)

## 安全中间态

OIDC issuer 曾为本机 pilot `:5556`。053 之后公网常态：`/api/v1/health` 可探，其余无有效 JWT → 401。正式 IdP 见 **[054](../PLAN-054-company-idp/)**。
