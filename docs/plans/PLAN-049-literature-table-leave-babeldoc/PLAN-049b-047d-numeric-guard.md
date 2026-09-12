# PLAN-049b：047d 数字邻居不合并

> 状态：已完成
> 父计划：[PLAN-049](./PLAN-049-literature-table-leave-babeldoc.md)

## 交付

`apply-pdf2zh-047d-para-layout.py` 的 Pass 1 / Pass 2：横向邻居若任一侧文本含数字且长度 ≤20，不 `_merge`。行尾无数字孤字（`of`）仍合并。
