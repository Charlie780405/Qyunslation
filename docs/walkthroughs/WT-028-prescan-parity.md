# WT-028 预扫描口径对齐交付记录

## 问题

`41467_2024_Article_53384.pdf` 预扫描报「检测到 0 处候选插图」，但翻译执行会 OCR 嵌字 12 处矢量多面板图；表格 19+ 处从未在 UI 提及。

## 根因

Tier-1 只扫 `get_image_info` 嵌入位图；该文仅 2 张首页 logo，几何门槛刷掉后为 0。矢量图与表格检测在 `pdf_figure_crop` / `find_tables`，未接入预扫描。

## 实现

| 组件 | 变更 |
|---|---|
| `pdf_figure_crop.py` | `table_rects` 公开；`find_safe_vector_figures(tables=)` |
| `doc_image_prescan.py` | `scan_pdf_tier3`、`format_tier3_summary` |
| `apply-pdf2zh-prescan.py` | Tier-3 挂链 + 代际守卫 |

## 验证

```bash
bash scripts/verify-plan-028.sh
```

预期：矢量 12、表格 ≥ 19、Tier-3 < 15s、gui 语法 OK。

## UI 预期文案

> 检测到 12 处矢量插图，将随文档一并翻译；另有 19 处表格，按文字层翻译。

表格不参与插图 OCR，正文与表内文字仍走 pdf2zh 文字层。
