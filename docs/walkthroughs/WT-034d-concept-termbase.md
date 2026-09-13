# WT-034d：Concept 术语库

对应 [PLAN-034d](../plans/PLAN-034-pharma-rd-mvp/PLAN-034d-concept-termbase.md)。

## 执行摘要

在 034c 关系库上新增 `concept` / `concept_term` / `concept_forbidden`；四层 curated CSV 可幂等导入；`build_merged_dict` 有库时优先读 curated 扁平视图，无库时仍走 CSV。API `POST /api/v1/concepts` 强制 staging。

## 用法

```bash
# 迁移（需 PG）
export QYUNSLATION_DATABASE_URL='postgresql+psycopg://qyunslation:qyunslation_dev_only@127.0.0.1:5433/qyunslation'
.venv/bin/python -m alembic -c alembic.ini upgrade head
.venv/bin/python scripts/plan034d-import-csv.py

# Dev API
export QYUNSLATION_DEV_AUTH_BYPASS=1
curl -sS -H 'X-Dev-User: a' -H 'X-Dev-Tenant: t' \
  -H 'Content-Type: application/json' \
  -d '{"preferred_source":"x","preferred_target":"译","status":"curated"}' \
  http://127.0.0.1:8010/api/v1/concepts
# → status 仍为 staging
```

**勿**入库 MedDRA 或真实 DB 密钥。

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/persist/test_plan034d_concept.py` | PASS |
| V2 | `bash scripts/verify-plan-034d.sh` | `SUMMARY: PASS` |
| V3 | 无引擎时 `build_merged_dict()` | ≥100 且含景行生物 |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/persist/models.py` | Concept 三表 |
| `qyunslation/persist/concept_repo.py` | 导入/API/forbidden |
| `qyunslation/glossary/concept_flatten.py` | 扁平 + TBX stub |
| `qyunslation/glossary/governance.py` | DB 优先 merge |
| `alembic/versions/034d0001_*.py` | 迁移 |
| `scripts/plan034d-import-csv.py` | CSV 导入 |
| `qyunslation/api/v1.py` | `/concepts` |
| `scripts/verify-plan-034d.sh` | 门禁 |
