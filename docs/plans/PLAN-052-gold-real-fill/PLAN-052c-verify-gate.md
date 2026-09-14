# PLAN-052c：门禁与 WT

> 状态：**已实现**
> 父计划：[PLAN-052](./PLAN-052-gold-real-fill.md)
> 验收：`bash scripts/verify-plan-052.sh` → `SUMMARY: PASS`（默认）

## 默认

1. 计划/WT/脚本存在
2. `pytest tests/gold/test_plan052*.py`
3. 打印 L/C/R real 计数与 `product_ready=yes|no`
4. **不**要求 R≥1

## 严格模式

`QYUNSLATION_PLAN052_REQUIRE_R_REAL=1`：R real=0 → `SUMMARY: BLOCKED`。

## 交付

- `scripts/verify-plan-052.sh`
- `docs/walkthroughs/WT-052-gold-real-fill.md`
- `docs/plans/README.md` 索引；051 回链
