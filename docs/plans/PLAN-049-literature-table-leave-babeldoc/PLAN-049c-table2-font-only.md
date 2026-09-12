# PLAN-049c：窄表只调字号

> 状态：已完成
> 父计划：[PLAN-049](./PLAN-049-literature-table-leave-babeldoc.md)

## 交付

文献跳过落笔后，仅当表区宽 <320pt 且高 <200pt（ljae439 表 2 量级）调用 `normalize_table_page(..., allow_translate=False)`。宽表 1/3 保持 BabelDOC 原样。
