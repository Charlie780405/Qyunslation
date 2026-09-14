# PLAN-054c：切流与门禁

> 父计划：[PLAN-054](./PLAN-054-company-idp.md)

## 步骤

1. 改 `/home/dev/pdf2zh/office.env` OIDC 四元组 → Authentik
2. `systemctl --user disable --now qyunslation-oidc-pilot.service`
3. `bash scripts/deploy-translate-stack.sh`
4. 更新 `scripts/office.env.example`（Authentik 占位，不再写 `:5556`）
5. `bash scripts/verify-plan-054.sh`

## verify-054 断言

| 组 | 判据 |
| --- | --- |
| 静态 | 文档 / compose / blueprint / Caddy `auth` 块 |
| 本机 | Authentik health；pilot `:5556` 已停 |
| 公网 | JWKS 200（DNS 未就绪 → BLOCKED） |
| E2E | client_credentials → 公网 projects/jobs/review enqueue |

053 门禁保持：pilot mint 不可达 → BLOCKED（不改语义）。

## 完成定义

- [x] `verify-plan-054.sh` → E2E 入队 PASS；公网 JWKS 无 DNS 时 **BLOCKED**（exit 2）
