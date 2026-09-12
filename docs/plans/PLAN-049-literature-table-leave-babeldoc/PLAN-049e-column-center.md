# PLAN-049e：文献表列内居中（只挪位）

> 状态：已实现
> 父计划：[PLAN-049](./PLAN-049-literature-table-leave-babeldoc.md)

## 目标

ljae439 最新译稿文字已在，但数据格从左往右流，未落在原文列中带内。第一次译稿（`38ba2d72`）数值中心约在 249–285 / 364–401 / 469–507。本期只按原文列几何把已有译文挪到列内居中。

## Out of Scope

- 整区 `redact_table_region` + `paint_fitted_blocks`
- 改字、补译、换模型
- Office / DOCX 建表
- 监管表单单元格回写

## 交付

1. `scripts/pdf_table_column_center.py`：`center_table_region(dest, origin, rect, x_shift)`
2. 列几何只来自**原文页**数据行空隙；左列标签左齐，其余列水平居中
3. `37.1 (13.3)` / `<10` / `40阴性` 各算一格；对不上格数的行跳过
4. 只 redact 被挪 span，`apply_redactions(images=0, graphics=0)`
5. 文献路径在 049c 字号归一**之后**调用（避免归一把居中写回 x0）

## 判据

- 合成夹具：数据 token 的 x 中心落入原文列中带
- 文献宽表无多列数据时仍 `dest==src`（049a 不回归）
- 模块内无 `redact_table_region` / `paint_fitted_blocks`
