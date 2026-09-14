# PLAN-054：正式公司 IdP（Authentik）

> 状态：**已实现**（公网 JWKS 待 DNS）
> 类型：自建 OIDC Issuer + 切流 sidecar
> 依赖：PLAN-034h、PLAN-053
> 验收：`bash scripts/verify-plan-054.sh`

## 文件索引

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 纲领 | [PLAN-054-company-idp.md](./PLAN-054-company-idp.md) | 目标与 Out of Scope |
| 054a | [PLAN-054a-authentik-deploy.md](./PLAN-054a-authentik-deploy.md) | compose + Caddy |
| 054b | [PLAN-054b-oidc-blueprint.md](./PLAN-054b-oidc-blueprint.md) | OIDC 契约 |
| 054c | [PLAN-054c-cutover-verify.md](./PLAN-054c-cutover-verify.md) | 切流与门禁 |

## 验收

```bash
bash scripts/deploy-plan-054-authentik.sh
bash scripts/plan054-apply-blueprint.sh
bash scripts/verify-plan-054.sh
```

Walkthrough：[WT-054-company-idp.md](../../walkthroughs/WT-054-company-idp.md)
