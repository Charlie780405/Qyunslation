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
