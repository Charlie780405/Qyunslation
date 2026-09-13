# WT-034g：人工审校工作台

对应 [PLAN-034g](../plans/PLAN-034-pharma-rd-mvp/PLAN-034g-human-review-bench.md)。

## 执行摘要

落地 `review_segment` / `review_note` / `review_revision`；`HUMAN_REVIEW` 入队、`PRESERVE` 跳过；批准写入正式 TM（034e）与可选术语 staging（034d）；版本 diff；最小页 `/static/review.html`。

## 权限

| 环境 | 身份 |
| --- | --- |
| 开发 | `QYUNSLATION_DEV_AUTH_BYPASS=1` + `X-Dev-User` / `X-Dev-Tenant` |
| 生产 | Dev 旁路禁用；OIDC → PLAN-034h |

页面路径（可替代实拍截图）：`http://127.0.0.1:8010/static/review.html`

## 用法

```bash
export QYUNSLATION_DATABASE_URL='postgresql+psycopg://qyunslation:qyunslation_dev_only@127.0.0.1:5433/qyunslation'
.venv/bin/python -m alembic -c alembic.ini upgrade head
export QYUNSLATION_DEV_AUTH_BYPASS=1
# 先 POST /api/v1/projects 与 /jobs，再打开 review.html 填 Job ID
```

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/persist/test_plan034g_review.py` | PASS |
| V2 | `bash scripts/verify-plan-034g.sh` | `SUMMARY: PASS` |
| V3 | 未批准 lookup | `reuse=false` |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/persist/models.py` | 审校三表 |
| `qyunslation/persist/review_repo.py` | 入队/决定/diff/建议 |
| `alembic/versions/034g0001_*.py` | 迁移 |
| `qyunslation/api/v1.py` | `/review/*` |
| `qyunslation/static/review.html` | 最小审校页 |
| `scripts/verify-plan-034g.sh` | 门禁 |
