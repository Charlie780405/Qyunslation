# WT-038d：纯图片表 cell 网格

日期：2026-09-10  
纲领：[PLAN-038d](../plans/PLAN-038-gap-closure/PLAN-038d-picture-tables.md)

## 交付

- `picture_table_region()` + `table_regions` 位图回退（`line_count=0`）
- `scan_pdf`：`Representation.BITMAP` + detector `picture_table`
- OCR cells 走既有 `structure_table` / `table_cell_policy`
- `tests/structure/test_plan038d_picture_table.py` / `scripts/verify-plan-038d.sh`

## 验收

```bash
bash scripts/verify-plan-038d.sh
```

## 关闭缺口

G-CAP-001
