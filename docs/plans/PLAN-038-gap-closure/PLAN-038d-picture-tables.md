# PLAN-038d：纯图片表 cell 网格（原 PLAN-034 一半）

> 状态：**已完成**
> 父计划：[PLAN-038](./PLAN-038-gap-closure.md)
> 归属缺口：G-CAP-001
> 验收：[WT-038d](../../walkthroughs/WT-038d-picture-tables.md) / `bash scripts/verify-plan-038d.sh`
> 前置：035/036 policy SSOT、033i `ocr_table_region` / `structure_table`

## 目标

当 PDF 表仅有题注、无线条/无文字层区域时：在题注下方圈定图像区域 → OCR 出 cell 网格 → 走 `table_cell_policy` → 写入 manifest `translatable_blocks`。失败 fail-closed（仅保留题注块）。

## 边界

- 不引入 Camelot/tabula
- 禁止第三套数字规则（只用 `classify_cell_policy`）
- 不改 DOCX/PPTX 跨页续表（G-CAP-009）

## 交付

1. `picture_table_region()`：题注下最大位图/渲染区 → `TableRegion`
2. `scan_pdf`：region 缺失时尝试 picture 回退
3. `tests/structure/test_plan038d_picture_table.py` + `scripts/verify-plan-038d.sh`
4. 回写 WT-030-table / WT-036 / ADR-030 遗留

## 验收

- 合成「题注 + 无文字层表图」夹具：`row_count/column_count >= 2` 且 cell 带 `translation_policy`
- `bash scripts/verify-plan-038d.sh` PASS
