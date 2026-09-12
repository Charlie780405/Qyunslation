# PLAN-034c：SaaS 持久化基础

> 状态：**待编码**（骨架文档）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：[034a](./PLAN-034a-gold-benchmark.md)

## 目标

引入 PostgreSQL + 版本化迁移、租户/项目模型与审计基础；**对象存储复用 PLAN-013 的 `StorageBackend`，不重建**。保留 `/service` 兼容层，新能力走 `/api/v1`。

## 现状

| 组件 | 现状 |
| --- | --- |
| 关系库 | **无** PG/SQLAlchemy/Alembic；仅有 SQLite 归档索引（`qyunslation/archive/index_db.py`） |
| 对象存储 | **已有** `StorageBackend` + `MinioStorageBackend`（`qyunslation/archive/storage.py`） |
| 任务状态 | 进程内字典 + asyncio（`server/core.py`），无跨进程持久任务 |

## 交付

1. PostgreSQL schema：`tenant`、`project`、`user_membership`、`job`、`audit_event` 最小集。
2. Alembic（或等价）版本化迁移；开发可用 docker-compose PG。
3. 审计：谁在何时对哪份源哈希做了何种操作（不含 API Key）。
4. API：`/api/v1/projects`、`/api/v1/jobs` 骨架；`/service/*` 继续可用。
5. 身份：生产 OIDC 适配器接口预留；开发旁路须显式环境变量且生产禁用（实现可在 034h 收口，034c 预留表与配置位）。

## 判据

- 迁移可空库 `upgrade` / `downgrade`。
- 对象存储路径仍走 `StorageBackend`；不引入第二套上传语义。
- 无 API Key 写入审计表。

## Out of Scope

- 完整 OIDC 生产对接（→ 034h）
- 术语/TM 业务表（→ 034d / 034e，可先留空 schema 占位）
- Celery/Redis 分布式队列（可后续；MVP 可先 DB 状态机）

## 完成定义

- [ ] PG 迁移 + 租户/项目 CRUD 冒烟
- [ ] `/api/v1` 与 `/service` 并存证明
- [ ] WT-034c 记录连接串约定（无密钥入库）
