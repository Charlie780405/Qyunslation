# WT-034e：翻译记忆 TM

对应 [PLAN-034e](../plans/PLAN-034-pharma-rd-mvp/PLAN-034e-translation-memory.md)。关闭历史悬空 [PLAN-001d4](../plans/PLAN-001-delivery-gpu-audit/PLAN-001-delivery-gpu-audit.md)（精确匹配层由本子计划交付；向量检索仍不做）。

## 执行摘要

在 034c/034d 之上新增 `tm_unit`（与 concept 分表）。仅 `approved=true` 入正式库；精确 = `source_norm` + `placeholder_sig`；模糊 ≥0.85 仅 `suggestions`（`reuse=false`）。提供 TMX 导入（默认未批准）/ 导出（仅批准）。**不**接 BabelDOC 自动套用。

## 用法

```bash
export QYUNSLATION_DATABASE_URL='postgresql+psycopg://qyunslation:qyunslation_dev_only@127.0.0.1:5433/qyunslation'
.venv/bin/python -m alembic -c alembic.ini upgrade head

export QYUNSLATION_DEV_AUTH_BYPASS=1
# 此接口只写 staging；approved=true 会 400。正式库走审校 decide
curl -sS -H 'X-Dev-User: a' -H 'X-Dev-Tenant: t' \
  -H 'Content-Type: application/json' \
  -d '{"source_text":"Primary endpoint","target_text":"主要终点"}' \
  http://127.0.0.1:8010/api/v1/tm/units

curl -sS -H 'X-Dev-User: a' -H 'X-Dev-Tenant: t' \
  -H 'Content-Type: application/json' \
  -d '{"source_text":"primary endpoint"}' \
  http://127.0.0.1:8010/api/v1/tm/lookup
```

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/persist/test_plan034e_tm.py` | PASS |
| V2 | `bash scripts/verify-plan-034e.sh` | `SUMMARY: PASS` |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/persist/models.py` | `TmUnit` |
| `qyunslation/persist/tm_repo.py` | 批准门禁 / lookup / 导入 staging |
| `qyunslation/tm/*` | normalize / match / tmx |
| `alembic/versions/034e0001_*.py` | 迁移 |
| `qyunslation/api/v1.py` | `/tm/units` `/tm/lookup` TMX |
| `scripts/verify-plan-034e.sh` | 门禁 |
