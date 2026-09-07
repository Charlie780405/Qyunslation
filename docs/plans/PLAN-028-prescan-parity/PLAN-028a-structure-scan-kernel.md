# PLAN-028a 子计划：结构扫描内核与表格结果共享

## 改动

### `scripts/pdf_figure_crop.py`

- `_table_rects` → 公开 `table_rects`，保留 `_table_rects = table_rects` 别名
- `find_safe_vector_figures(page, exclude_rects=None, *, tables=None)`：`tables is None` 时内部计算

### `scripts/doc_image_prescan.py`

- `Tier3Result`：`vector_count`、`table_count`、`pages_scanned`、`truncated`
- `scan_pdf_tier3(path, *, max_pages, deadline_s, should_abort)`：每页一次 `table_rects`，传入矢量聚类
- `format_tier3_summary(entry, *, vector_count, table_count, truncated, pages_scanned)`：合并位图/矢量/表格文案

## 环境变量

- `QYUNSLATION_PRESCAN_TIER3_MAX_PAGES`（默认 40）
- `QYUNSLATION_PRESCAN_TIER3_DEADLINE`（默认 25s）

## 验收

- `41467_2024_Article_53384.pdf`：`vector_count == 12`，`table_count >= 19`，耗时 < 15s
- 传入 `tables=` 与不传，同页矢量区域一致
