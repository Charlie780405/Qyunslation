# PLAN-054b：OIDC 应用契约（Blueprint）

> 父计划：[PLAN-054](./PLAN-054-company-idp.md)

## 目标

可重复 blueprint 落盘 Provider + Application + `tenant` ScopeMapping；M2M 用 client_credentials 取 JWT。

## 契约

| 项 | 值 |
| --- | --- |
| Application slug | `qyunslation` |
| issuer | `https://auth.qyunsgen.com/application/o/qyunslation/` |
| audience / client_id | `qyunslation` |
| JWKS | `https://auth.qyunsgen.com/application/o/qyunslation/jwks/` |
| tenant claim | JWT `tenant`（默认 `pilot`） |
| 签名 | RS256 |
| M2M | `grant_type=client_credentials` + provider `client_secret`（自动 service account） |

## 交付

- `deploy/authentik/blueprints/qyunslation-oidc.yaml`
- `scripts/plan054-apply-blueprint.sh`（bootstrap token 导入 / 或挂载自动加载）

## 完成定义

- [x] ScopeMapping `tenant` 存在
- [x] Provider + Application `qyunslation` 存在
- [x] 本机 token 端点可发含 `tenant` 的 JWT
