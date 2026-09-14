# PLAN-054：正式公司 IdP（自建 Authentik）

> 状态：**已实现**（工程门绿；公网 `auth.qyunsgen.com` JWKS 待 Cloudflare DNS → verify **BLOCKED**）
> 日期：2026-09-13
> 依赖：PLAN-034h（OidcAdapter）、PLAN-053（公网 `/api/v1`）
> 验收门：`bash scripts/verify-plan-054.sh`
> Walkthrough：[WT-054](../../walkthroughs/WT-054-company-idp.md)

## 一句话

自建 Authentik（`auth.qyunsgen.com`）作为 OIDC Issuer，用 blueprint/API 配好 `qyunslation` audience 与 `tenant` claim，切换 `office.env` 后关掉本机 `:5556` pilot。

## 现状

| 层 | 状态 |
| --- | --- |
| sidecar Resource Server | 已有（034h，只读 env） |
| 公网 `/api/v1` | 已有（053） |
| issuer | **Authentik :9000**（pilot 已停） |
| 公网 JWKS DNS | **待 Cloudflare 加 `auth` 记录** |

## 子计划

| ID | 交付 |
| --- | --- |
| [054a](./PLAN-054a-authentik-deploy.md) | compose `:9000` + Caddy `auth` + deploy 脚本 |
| [054b](./PLAN-054b-oidc-blueprint.md) | Provider/App/`tenant` mapping + M2M |
| [054c](./PLAN-054c-cutover-verify.md) | 切 env、停 pilot、verify-054 |

## Out of Scope

- 迁 qyunsgen NextAuth / 微信用户进 Authentik
- `review.html` Authorization Code + PKCE
- `/service/*`、`/docs` 公网暴露
- Cloudflare Access、Keycloak
- 流水线自动 `review/enqueue`

## 完成定义

- [x] 纲领 + 054a/b/c + README + WT-054；plans 索引与 051/053 回链
- [x] Authentik 本机健康；Caddy `auth.qyunsgen.com` → `:9000`
- [x] OIDC 契约就绪（API 幂等 + blueprint SSOT）；issuer/aud/tenant 对齐
- [x] office.env 切 Authentik；pilot 停；`verify-plan-054.sh` E2E 入队 PASS（公网 JWKS 无 DNS → BLOCKED）
