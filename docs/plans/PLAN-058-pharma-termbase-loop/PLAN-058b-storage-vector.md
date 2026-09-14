# PLAN-058b：关系库、项目隔离与 ConceptTerm 向量

> 父计划：[PLAN-058](./README.md)

## 交付

- PostgreSQL 为正式术语事实源；迁移 `058a0001` 增加项目字段、规范化字段、候选/位置/决定表。
- 生产 PostgreSQL 使用 `pgvector` 1024 维 cosine/HNSW；SQLite 使用 JSON 便于本地测试。
- ConceptTerm embedding 通过泰州 bge-m3 sidecar 回填；sidecar 失败不影响精确路径。
- 任何 runtime 查询同时过滤 tenant、project、language、status 和 curated 状态。

## 完成定义

- SQLite fresh upgrade 可完成，已有行不会丢失。
- 词库版本随 Concept version/更新时间变化，旧策略缓存自动失效。
- embedding 只服务语义建议，不与 TM 向量表混用。
