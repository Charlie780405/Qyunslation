# PLAN-053a：Caddy `/api/v1` 路由

> 父计划：[PLAN-053](./PLAN-053-saas-caddy-expose.md)

## 目标

在 `translate.qyunsgen.com` 站点块新增 matcher，将 `/api/v1/*` 反代到 sidecar `127.0.0.1:8010`，且不影响 Gradio `:7860` 兜底。

## 改动面

- SSOT：`/home/dev/qyunsgen/config/Caddyfile-production-public`（qyunsgen 仓，本号只改工作区、不提交）
- 部署：`scripts/deploy-plan-053-api-expose.sh`（备份 → awk 校验 → `caddy validate` → `reload` → 冒烟）

## 路由规则

```caddy
@qy_api path /api/v1/*

handle @qy_api {
    reverse_proxy 127.0.0.1:8010 {
        transport http {
            read_timeout 120s
            write_timeout 120s
        }
        header_up Host {host}
        header_up X-Forwarded-Proto https
        header_up X-Forwarded-Host {host}
    }
    header Cache-Control "no-store"
}
```

`handle @qy_api` 必须写在兜底 `handle { ... 7860 }` **之前**。

## 刻意不暴露

- `/service/*`（可选 API_TOKEN，未配则裸奔）
- `/docs`、`/openapi.json`
- `/static/review.html`

## 回滚

恢复 Caddyfile 备份后 `docker exec qyunsgen-caddy caddy reload --config /etc/caddy/Caddyfile`。

## 完成定义

- [x] translate 块含 `@qy_api` / `127.0.0.1:8010`
- [x] deploy 脚本可重复执行；reload 后公网 `/api/v1/health` ≠ 404
