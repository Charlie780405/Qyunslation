# PLAN-045e：文献表格字号 source_p75

> 状态：已完成
> 父计划：[PLAN-045](./PLAN-045-literature-pdf-fidelity.md)

## 交付

1. `isolate_residue` 仅 REGULATORY；`normalize_table_sizes` 对 REGULATORY 或 RESEARCH/REVIEW。
2. `fit_group(table_size_mode=)`：`ladder`（监管）/ `source_p75`（文献）。
3. 文献 floor：header/cell ≥7，footnote ≥5.5。

## 验收

- `tests/structure/test_plan045_table_size.py`；044 ladder 不回退
