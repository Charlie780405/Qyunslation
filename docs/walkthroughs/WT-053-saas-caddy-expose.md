# WT-053：SaaS 接线（Caddy 对外 /api/v1）

对应 [PLAN-053](../plans/PLAN-053-saas-caddy-expose/PLAN-053-saas-caddy-expose.md)。把 034 已实现的 sidecar `/api/v1`（含 review 入队）挂到 `translate.qyunsgen.com`。

## 执行摘要

Caddy translate 块新增 `@qy_api path /api/v1/*` → `127.0.0.1:8010`。不暴露 `/service`。production 下强制 OIDC；公网负向断言证明可达且锁死。正向 E2E 用本机 pilot IdP mint JWT。

## 部署

```bash
bash scripts/deploy-plan-053-api-expose.sh
```

- 备份：`/home/dev/qyunsgen/config/Caddyfile-production-public.bak-053-*`
- validate + reload：容器 `qyunsgen-caddy`
- 回滚：还原备份后 `docker exec qyunsgen-caddy caddy reload --config /etc/caddy/Caddyfile`

## 验证

```bash
bash scripts/verify-plan-053.sh
```

期望：`SUMMARY: PASS fail=0`。pilot IdP 宕机时正向段 **BLOCKED**。

## 冒烟（手工）

```bash
curl -fsS https://translate.qyunsgen.com/api/v1/health
# → {"schema":"...","db":"ok"}  无 env 字段

curl -sS -o /dev/null -w '%{http_code}\n' https://translate.qyunsgen.com/api/v1/projects
# → 401

curl -sS -o /dev/null -w '%{http_code}\n' https://translate.qyunsgen.com/service/meta
# → 404
```

## 下一步

- **[054](./WT-054-company-idp.md)** 正式公司 IdP（Authentik，替换 `:5556` pilot）
- 流水线自动 `review/enqueue`（本号未做）
