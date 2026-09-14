# WT-054：正式公司 IdP（Authentik）

对应 [PLAN-054](../plans/PLAN-054-company-idp/PLAN-054-company-idp.md)。用 Authentik 替换本机 `:5556` pilot，作为 `translate.qyunsgen.com/api/v1` 的正式 OIDC Issuer。

## 执行摘要

1. `deploy/authentik` compose → `127.0.0.1:9000`
2. Caddy `auth.qyunsgen.com` → `:9000`
3. Blueprint：Application `qyunslation` + `tenant` scope + M2M client_credentials
4. `office.env` 切 issuer/jwks；停 `qyunslation-oidc-pilot`
5. `verify-plan-054.sh` 公网 E2E

## 部署

```bash
# 首次：复制 .env.example → deploy/authentik/.env，填密钥与 bootstrap
cp deploy/authentik/.env.example deploy/authentik/.env
# 编辑 .env 后：
bash scripts/deploy-plan-054-authentik.sh
bash scripts/plan054-apply-blueprint.sh
```

DNS：Cloudflare 增加 `auth.qyunsgen.com`（与 translate 同源、Proxied）。**当前未配置时** `verify-plan-054.sh` 对公网 JWKS 判 **BLOCKED**；sidecar 使用本机 `http://127.0.0.1:9000/.../jwks/`，公网 `/api/v1` E2E 仍可绿。

## 验证

```bash
bash scripts/verify-plan-054.sh
```

期望：DNS 就绪后 `SUMMARY: PASS`；否则 `SUMMARY: BLOCKED`（fail=0）且 E2E enqueue PASS。

## 契约速查

| 项 | 值 |
| --- | --- |
| issuer | `https://auth.qyunsgen.com/application/o/qyunslation/` |
| audience | `qyunslation` |
| JWKS | `https://auth.qyunsgen.com/application/o/qyunslation/jwks/` |
| tenant claim | `tenant` |

## 下一步

- 浏览器登录（Authorization Code + PKCE）/ 审校台
- **[055](./WT-055-tm-vector-embed.md)** TM 向量 + 泰州 bge-m3 MCP
