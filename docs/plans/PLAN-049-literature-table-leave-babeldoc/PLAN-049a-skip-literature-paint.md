# PLAN-049a：文献表不落笔

> 状态：已完成
> 父计划：[PLAN-049](./PLAN-049-literature-table-leave-babeldoc.md)

## 交付

`translate_pdf_tables`：`RESEARCH_ARTICLE` / `REVIEW_ARTICLE` 在 `not_a_table` 之后一律 `EXPLICITLY_SKIPPED` / `literature_leave_babeldoc`，不调用 `redact_table_region` / `paint_fitted_blocks`。

`NOT_A_TABLE` 仍交图片链，不在此做字号涂改。
