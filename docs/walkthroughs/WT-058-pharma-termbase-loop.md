# WT-058：医药术语闭环与混合检索

> 计划：[PLAN-058](../plans/PLAN-058-pharma-termbase-loop/README.md)
> 分支：`codex/plan-058-pharma-termbase-loop`

## 当前实现

本 WT 用来记录每次验收，不把离线单测等同于真实医药金标质量。

| 项目 | 结果 |
| --- | --- |
| 术语 resolver / alias 快路径 | 已实现，精确路径不调用 embedding |
| 项目/租户隔离与 ConceptTerm | 已实现 |
| SQLite 迁移回归 | 已通过 |
| PostgreSQL pgvector 修复迁移 | `058b0001` 已实现，待目标库执行 |
| 人工候选与乐观锁裁决 | 已实现 |
| 策略注入与译后 QA | 已实现；二进制写回报告 unavailable |
| bge-m3 / PostgreSQL LIVE | 待当前环境执行 |
| 1,000 出现、300 Concept、20 文件金标 | 待提供/执行 |

## 默认工程门

```bash
bash scripts/verify-plan-058.sh
```

允许显式指定解释器：

```bash
QYUNSLATION_VERIFY_PY=/path/to/python bash scripts/verify-plan-058.sh
```

## LIVE 产品门

金标 JSON 需包含：

```json
{
  "gold": [{"source_term": "primary endpoint", "concept_id": "c1", "exact": true}],
  "predictions": [{"source_term": "primary endpoint", "concept_id": "c1", "match_type": "exact", "confidence": 1.0}]
}
```

执行：

```bash
QYUNSLATION_PLAN058_LIVE=1 \
QYUNSLATION_PLAN058_GOLD=/path/to/plan058-gold.json \
bash scripts/verify-plan-058.sh
```

LIVE 缺数据库、金标、pgvector 或泰州 bge-m3 时，结果必须是 `BLOCKED`；质量指标不足是 `FAIL`。

## 续接记录

后续在此补充：同一术语第二次翻译是否停在 L1/L2、实际 embedding 调用次数、五项指标、越界测试、依赖门结果和提交/推送 SHA。

## 合并前验证记录（2026-09-14）

| 验证项 | 结果 |
| --- | --- |
| PLAN-058 专项门禁 | PASS；专项测试与静态检查通过 |
| Python 编译检查 | PASS |
| 完整回归 | 881 passed、12 failed、6 skipped；未标记为全绿 |
| 基线对照 | 11 个结构/表格失败在 `origin/main` 定向复现；全量运行中的 logger 失败单测独立运行通过 |
| 真实金标 / PostgreSQL / 泰州 bge-m3 LIVE | 本环境未执行，交由 Cursor 环境续接 |

完整回归失败不归因于 PLAN-058 专项改动；生产上线仍需在目标环境完成真实 LIVE 门及依赖门。

## 生产交付记录（2026-09-14）

| 项目 | 结果 |
| --- | --- |
| 合并 / 远程 | `main` 与 `origin/main` 均为 `7736871`；功能分支已同步 |
| 生产依赖 | `uv sync --frozen`；Python `pgvector==0.5.0` |
| PostgreSQL | `pgvector/pgvector:pg16`，持久卷未删除；扩展 0.8.6 |
| 数据库迁移 | `058b0001`；向量列为 `vector(1024)`，HNSW 索引存在 |
| 迁移前备份 | `/tmp/qyunslation-pre-058-807b2bb.dump` |
| 服务部署 | `deploy-translate-stack.sh` PASS；pdf2zh 与 qyunslation-office active |
| 健康检查 | 本地与 `https://translate.qyunsgen.com/api/v1/health` 均 PASS |
| sidecar 指纹 | `e85db39ed8e5`，本地/远端一致 |
| 泰州 bge-m3 | 探活 PASS；模型名 `bge-m3`，返回 1024 维非零向量 |
| 真实金标质量门 | 待 Cursor 环境提供金标 JSON 后执行；当前不宣称通过 |

首次迁移曾因旧 PostgreSQL 镜像缺少 `vector` 扩展而事务回滚；切换同一持久卷到 pgvector 镜像并应用 058b 修复后已收口。数据库仍报告既有 libc collation 版本告警，未在本次交付中重建业务索引。
