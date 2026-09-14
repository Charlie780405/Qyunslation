# PLAN-054a：Authentik 部署 + Caddy

> 父计划：[PLAN-054](./PLAN-054-company-idp.md)

## 目标

独立 compose 起 Authentik（`127.0.0.1:9000`），Caddy 加 `https://auth.qyunsgen.com` → `:9000`。

## 交付

| 路径 | 说明 |
| --- | --- |
| `deploy/authentik/docker-compose.yml` | postgresql + redis + server + worker |
| `deploy/authentik/.env.example` | 密钥占位（真实 `.env` gitignore） |
| `scripts/deploy-plan-054-authentik.sh` | up + 健康检查 + Caddy reload |

## Caddy

在 `Caddyfile-production-public` 增加 `auth.qyunsgen.com` 块（Origin Cert + `X-Forwarded-Proto`）。qyunsgen 仓只留工作区 diff。

## DNS

Cloudflare：`auth.qyunsgen.com` → 与 translate 同源、Proxied。未就绪时本机通、公网 JWKS **BLOCKED**。

## 完成定义

- [x] `curl -fsS http://127.0.0.1:9000/-/health/live/` 成功
- [x] Caddyfile 含 `auth.qyunsgen.com` 与 `127.0.0.1:9000`
