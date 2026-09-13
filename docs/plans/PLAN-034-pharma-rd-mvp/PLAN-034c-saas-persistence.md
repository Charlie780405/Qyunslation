# PLAN-034c：SaaS 持久化基础

> 状态：**已实现**
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034a](./PLAN-034a-gold-benchmark.md)（样本门；本项不依赖金标二进制）
> 证据：[WT-034c](../../walkthroughs/WT-034c-saas-persistence.md)
> 验收：`bash scripts/verify-plan-034c.sh`

## 目标

引入 PostgreSQL + 版本化迁移、租户/项目模型与审计基础；**对象存储复用 PLAN-013 的 `StorageBackend`，不重建**。保留 `/service` 兼容层，新能力走 `/api/v1`。

## 现状（实现后）

| 组件 | 现状 |
| --- | --- |
| 关系库 | SQLAlchemy 2 + Alembic + psycopg；表 `tenant` / `project` / `user_membership` / `job` / `audit_event` |
| 对象存储 | 仍用 `StorageBackend`；job 仅可选 `storage_key` |
| `/service` 任务 | 仍为进程内 `tasks_state`（**未**桥接到 `job`） |
| `/api/v1` | health / projects / jobs 骨架 |

## 交付

1. PostgreSQL schema：`tenant`、`project`、`user_membership`、`job`、`audit_event` 最小集。
2. Alembic 版本化迁移；开发用 `docker-compose.plan034c.yml`。
3. 审计：谁在何时对哪份源哈希做了何种操作（剥离 API Key / Authorization）。
4. API：`/api/v1/projects`、`/api/v1/jobs` 骨架；`/service/*` 继续可用。
5. 身份：`DevBypassAdapter`（显式 env）；`OidcAdapter` 桩 → 034h。

## 判据

- 迁移可空库 `upgrade` / `downgrade`（需设置 `QYUNSLATION_DATABASE_URL`）。
- 对象存储路径仍走 `StorageBackend`；不引入第二套上传语义。
- 无 API Key 写入审计表。
- pytest 用 SQLite 内存库，**不强制** Docker。

## Out of Scope

- 完整 OIDC 生产对接（→ 034h）
- 术语/TM 业务表（→ 034d / 034e）
- Celery/Redis；`/service/translate` → `job` 持久化桥接

## 完成定义

- [x] PG 迁移 + 租户/项目 CRUD 冒烟（SQLite 单测 + Alembic revision）
- [x] `/api/v1` 与 `/service` 并存证明
- [x] WT-034c 记录连接串约定（无密钥入库）
