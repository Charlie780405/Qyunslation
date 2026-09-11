# PLAN-042d：单元格归属与键值配对

> 状态：**已完成**
> 父计划：[PLAN-042](./PLAN-042-regulatory-translation-quality.md)

## 交付

1. `qyunslation/structure/table_attribution.py`：标签-值配对断言、跨格合并检测。
2. `table_writeback.redact_source_blocks`：按单元格 bbox 膨胀覆盖多行源 span。
3. QC 码 `LABEL_VALUE_SHIFT` / `CELL_MERGE` 进表格硬门禁。

## 验收

- 标签与值零行偏移（合成键值对夹具）。
- 多行源 span 中文残留为零。
