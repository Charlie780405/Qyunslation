# PLAN-046a：止血门禁

> 状态：已完成
> 父计划：[PLAN-046](./PLAN-046-literature-structure-fidelity.md)

## 交付

1. literature 退出 `isolate_residue`；`if literature: source_p75` 优先于 ladder。
2. `COLUMN_CLUSTER_DRIFT` 前置门禁（碎片格 / 列稀疏）→ 整表跳过。
3. `FIGURE_TIER_MAX_PX=72`；擦除前试排，放不下则 `C5_SKIPPED` 不擦不画。
4. `patch_literature_typesetting` 改为只告警不裁字。

## 验收

- `tests/structure/test_plan046a_gates.py`
- `tests/extensions/test_plan046a_size_cap.py`
