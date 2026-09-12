# PLAN-045e：文献表格字号 source_p75

> 状态：已完成
> 父计划：[PLAN-045](./PLAN-045-literature-pdf-fidelity.md)

## 交付

1. `normalize_table_sizes` 对 REGULATORY 或 RESEARCH/REVIEW。
2. `fit_group(table_size_mode=)`：`ladder`（监管）/ `source_p75`（文献）。
3. 文献 floor：header/cell ≥7，footnote ≥5.5。
4. **热修**：文献也开 `isolate_residue`（OVERFLOW 在 paint 前硬失败则 `.tbltr` 永不写出）。`SOURCE_RESIDUE` 仅中文源；`source_p75` 不把溢出格差记成 `ROLE_SIZE_DRIFT`。

## 验收

- `tests/structure/test_plan045_table_size.py`；044 ladder 不回退
