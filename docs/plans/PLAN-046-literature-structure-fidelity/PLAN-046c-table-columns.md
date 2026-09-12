# PLAN-046c：表格列重建

> 状态：已完成
> 父计划：[PLAN-046](./PLAN-046-literature-structure-fidelity.md)

## 交付

1. `_merge_column_clusters`：小间隙合并格内碎片。
2. 单元格 bbox = 列带 ∪ 墨迹并集。
3. `SPAN_ORDER_DRIFT` 运行时检测，进 `TABLE_TERMINAL_FAIL`。

## 验收

- `tests/structure/test_plan046c_columns.py`
- ljae439 Table 1：`37.1 (13.3)` 完整；列数从 14 → ≤5
