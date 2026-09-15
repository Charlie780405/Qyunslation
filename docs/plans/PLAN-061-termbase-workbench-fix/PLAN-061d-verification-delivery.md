# PLAN-061d：回归、部署与 WT

> 父计划：[PLAN-061](./README.md)

- 专项：`tests/workbench/test_plan061_*.py`、`tests/ui/test_plan061_workbench_patch.py`，并回归 PLAN-060 evidence/bridge/ui。
- 门禁：`bash scripts/verify-plan-061.sh`；`QYUNSLATION_PLAN061_LIVE=1` 探活 provider 与 alembic；`QYUNSLATION_PLAN061_FULL=1` 跑 060/058。
- 部署必须 `python3 scripts/apply-pdf2zh-060-termbase-workbench.py` 后走 `deploy-translate-stack.sh`（指纹只覆盖 sidecar，GUI patch 需单独记证据）。
- 走查：[WT-061](../../walkthroughs/WT-061-termbase-workbench-fix.md)。
