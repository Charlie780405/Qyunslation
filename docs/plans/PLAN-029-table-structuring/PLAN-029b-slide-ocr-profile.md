# PLAN-029b 幻灯片 OCR 嵌字破例

## 背景

Hermes [`is_slide_page`](/home/dev/Hermes/scripts/lit_tables.py) 判定宽高比 ≥ 1.55。幻灯页 `find_tables` 会把条形图当表，`caption_table_clip` 也不适用，表格译文只能走 OCR 嵌字。

## 标定结果（17 页 16:9 样本）

| 参数 | 期刊默认 | 幻灯 profile |
|---|---|---|
| `TEXT_OVERLAP_MAX` | 0.10 | **0.50** |
| `MAX_AREA_FRAC` | 0.80 | 0.80 |
| `MIN_DRAWINGS` | 8 | **6** |
| 表格避让 | 是 | **否**（`tables=[]`） |

矢量区域：8 → 12（+50%），期刊样本仍为 12（零回归）。

## 实现

### `scripts/pdf_figure_crop.py`

- `is_slide_page(page)` 与 Hermes 同口径
- `find_safe_vector_figures(..., text_overlap_max=, max_area_frac=, min_drawings=)`
- 常量 `SLIDE_TEXT_OVERLAP` / `SLIDE_MAX_AREA_FRAC` / `SLIDE_MIN_DRAWINGS`

### `scripts/pdf_image_translate.py`

策略 B 按页判型：

```python
slide = is_slide_page(page)
figures = find_safe_vector_figures(
    page, exclude_rects=exclude,
    tables=[] if slide else None,
    text_overlap_max=SLIDE_TEXT_OVERLAP if slide else None,
    max_area_frac=SLIDE_MAX_AREA_FRAC if slide else None,
    min_drawings=SLIDE_MIN_DRAWINGS if slide else None,
)
```

## 质量

- `area_frac > max_area_frac` 仍 Fail-Closed，绝不整页覆盖
- `policy.evaluate_image_candidate` 与 OCR QC 不放宽
