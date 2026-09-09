# PLAN-033e：当前页 300 DPI 懒加载预览

> 状态：**已完成**（`verify-plan-033e.sh` PASS）
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 前置：033c（预览吃的是 BabelDOC 输出，须先保证原文半边干净）

## 目标

预览只对**当前可见页**按 300 DPI 渲染；其它页保持低 DPI 占位。进度条用 manifest 语义对象数，不用内部 OCR 步数。

## 不做什么

- 整份 PDF 预生成 300 DPI
- 改扫描器、题注、表格几何

## 做法

1. `pdf_preview_pages.py`：当前页 300 DPI，其余 72 DPI 占位。
2. `apply-pdf2zh-preview-dpi.py`：GUI 记下当前页并用 300/72 标记；挂在 viewer 之后。
3. `progress.format_semantic_progress`：`已处理 图 1/2 · 表 2/4`；docimg 后处理进度走 manifest 计数。

## 验收

| # | 预期 |
| --- | --- |
| V1 | 非当前页不出现 300 DPI pixmap |
| V2 | 当前页长边像素 ≈ 页 pt × 300/72 |
| V3 | 进度分母来自 figure+table 计数 |
