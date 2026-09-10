# WT-030-table：PDF 三线表单元格网格收口

> 日期：2026-09-10  
> HEAD：见 merge commit  
> 纲领：[PLAN-030-table](../plans/PLAN-030-semantic-layout-translation/PLAN-030-table-pdf-cell-reconstruction.md)  
> ADR：[ADR-030-table-cell-extraction](../decisions/ADR-030-table-cell-extraction.md)

## 交付

- Task 0：`scripts/spike-plan030-table-task0.py` → 采纳 033i 自研 `table_structure`，不引入 camelot/tabula
- `table_grid_dimensions()` + `scan_pdf` 写入 `row_count`/`column_count`
- 门禁：`bash scripts/verify-plan-030-table.sh`

## 验证

| # | 步骤 | 结果 |
| --- | --- | --- |
| V1 | `verify-plan-030-table.sh` | PASS |
| V2 | `test_table_protection.py` 回归 | PASS |
| V3 | ljae439 + Nature 6 表 `row_count/column_count >= 2` | PASS |

## 部署

```bash
systemctl --user restart pdf2zh.service qyunslation-office.service
bash scripts/verify-plan-030-table.sh
bash scripts/verify-plan-030i.sh
```

## 遗留

- 跨页续表：已由 [PLAN-035](../plans/PLAN-035-table-execution-fidelity/PLAN-035-table-execution-fidelity.md) + [PLAN-036](../plans/PLAN-036-table-policy-unification/PLAN-036-table-policy-unification.md)（Wiley reference 金样）承接
- 纯图片表：仍 out of scope
- `glossaries/auto-proper-nouns.csv`：运行时 harvest，不提交
