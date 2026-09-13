# WT-034c：SaaS 持久化基础

对应 [PLAN-034c](../plans/PLAN-034-pharma-rd-mvp/PLAN-034c-saas-persistence.md)。

## 执行摘要

落地 SQLAlchemy 2 + Alembic + 五表最小 SaaS 模型，挂 `/api/v1` 骨架；`/service` 不变。对象存储仍走既有 `StorageBackend`。术语/TM 表不建。

## 环境变量（无密钥入库）

| 变量 | 说明 |
| --- | --- |
| `QYUNSLATION_DATABASE_URL` | 例：`postgresql+psycopg://qyunslation:qyunslation_dev_only@127.0.0.1:5433/qyunslation` |
| `QYUNSLATION_DEV_AUTH_BYPASS` | `1` 时启用 Dev 旁路（**production 禁用**） |
| `QYUNSLATION_ENV` | `production` 时拒绝 Dev 旁路 |
| `X-Dev-User` / `X-Dev-Tenant` | 旁路请求头（默认 `dev-user` / `dev`） |

**勿**把真实数据库密码、生产连接串写入 git。compose 默认口令仅供本机开发。

## 本机 PostgreSQL

```bash
docker compose -f docker-compose.plan034c.yml up -d
export QYUNSLATION_DATABASE_URL='postgresql+psycopg://qyunslation:qyunslation_dev_only@127.0.0.1:5433/qyunslation'
.venv/bin/python -m alembic -c alembic.ini upgrade head
# 回滚：.venv/bin/python -m alembic -c alembic.ini downgrade -1
```

端口 **5433**（避免与本机其它 PG 冲突）。

## API 冒烟

```bash
export QYUNSLATION_DEV_AUTH_BYPASS=1
curl -sS http://127.0.0.1:8010/api/v1/health
curl -sS -H 'X-Dev-User: alice' -H 'X-Dev-Tenant: demo' \
  -H 'Content-Type: application/json' \
  -d '{"slug":"p1","name":"Project One"}' \
  http://127.0.0.1:8010/api/v1/projects
# /service/meta 仍可用
curl -sS http://127.0.0.1:8010/service/meta
```

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/persist/test_plan034c_*.py` | PASS |
| V2 | `bash scripts/verify-plan-034c.sh` | `SUMMARY: PASS`（无 URL 时跳过 live alembic） |
| V3 | git 无真实 DB 密钥 | 干净 |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/persist/*` | 模型 / Session / 审计 / 身份 / repo |
| `qyunslation/api/v1.py` | `/api/v1` 骨架 |
| `alembic/` + `alembic.ini` | 首版五表 |
| `docker-compose.plan034c.yml` | 本机 PG16 |
| `scripts/verify-plan-034c.sh` | 034c 门 |
