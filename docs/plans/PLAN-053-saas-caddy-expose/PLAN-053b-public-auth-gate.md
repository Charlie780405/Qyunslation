# PLAN-053b：公网鉴权门禁

> 父计划：[PLAN-053](./PLAN-053-saas-caddy-expose.md)

## 目标

`scripts/verify-plan-053.sh` 证明：公网 `/api/v1` 可达、匿名不漏配置、无 Bearer→401、dev 旁路→403、未暴露 `/service`，以及本机 mint 后公网 E2E 入队。

## 断言组

### 静态

- 053 纲领 / 053a / 053b / README / WT-053 / deploy / verify 脚本存在
- Caddyfile translate 块含 `/api/v1` 与 `127.0.0.1:8010`
- `caddy validate` 通过（容器内）

### 公网负向

| 请求 | 期望 |
| --- | --- |
| `GET /api/v1/health` | 200；含 `schema`；**不含** `env` / `database_url_set` |
| `GET /api/v1/projects`（无 Bearer） | 401 |
| 同上 + `X-Dev-User` / `X-Dev-Tenant` | 401（旁路未开）或 403（旁路误开被拒） |
| `GET /service/meta` | 404 |

### 公网正向 E2E

1. 本机 `POST http://127.0.0.1:5556/token`（`QYUNSLATION_OIDC_MINT_SECRET`）拿 JWT
2. 公网：`POST /api/v1/projects` → `POST /api/v1/jobs` → `POST /api/v1/review/enqueue` → `GET /api/v1/review/queue`
3. 入队 `count ≥ 1`

pilot IdP / mint 不可达 → **BLOCKED**（exit 2），不是 FAIL。

## 完成定义

- [x] `bash scripts/verify-plan-053.sh` → `SUMMARY: PASS`
