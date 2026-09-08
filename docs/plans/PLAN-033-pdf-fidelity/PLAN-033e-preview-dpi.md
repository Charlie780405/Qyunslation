# PLAN-033e：当前页 300 DPI 懒加载预览

> 状态：**已设计，未实施**
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 前置：033c（预览吃的是 BabelDOC 输出，须先保证原文半边干净）

## 目标

预览只对**当前可见页**按 300 DPI 渲染；其它页保持低 DPI 占位。进度条用 manifest 语义对象数，不用内部 OCR 步数。

## 不做什么

- 整份 PDF 预生成 300 DPI
- 改扫描器、题注、表格几何

## 做法（待施工）

1. 查 `apply-pdf2zh-viewer.py` / dual-preview 现有 pixmap DPI。
2. 当前页请求升到 300；翻页再渲染，已渲染页缓存。
3. 进度文案：`已处理 图 1/2 · 表 2/4`，不暴露 RapidOCR 内部步。

## 验收

| # | 预期 |
| --- | --- |
| V1 | 非当前页不出现 300 DPI pixmap |
| V2 | 当前页长边像素 ≈ 页 pt × 300/72 |
| V3 | 进度分母来自 figure+table 计数 |
