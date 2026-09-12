# PLAN-049f：表内西文半角 + 原文行列对齐

> 状态：已实现
> 父计划：[PLAN-049](./PLAN-049-literature-table-leave-babeldoc.md)

## 目标

049e 把数字推进列后，`china-s` 把拉丁拉开成全角间距；表1 NRS/DLQI 的 `N=` 续行被 skip；表3 多段 dest 并到一行后叠墨、`每4周` 未还原为 `Q4W`。本期：非汉字半角英文（Helvetica）、按原文视觉行 y 落笔、数据续行不跳过。

## Out of Scope

- 整区 `redact_table_region` + `paint_fitted_blocks`
- 改中文词义 / 补译 / 换模型
- 表头碎段 `(N=130)` 重建
- Office 建表；监管表单

## 交付

1. `normalize_ascii`：全角 `U+FF01–U+FF5E` 折半角；汉字不动
2. origin 格为 `Q2W`/`Q4W`/`NA` 等时，dest 的 `每4周` 写回短写
3. 混排落笔：CJK → `china-s`，其余 → `helv`
4. 基线用原文行 y；数据 `N=` 续行不 skip；表头 `(N=130)` 仍 skip
5. 擦除用 origin 行 y 带 × 全表宽；`|Δcy|>4` 的 dest 片段不 merge

## 判据

- 表内无全角括号；`Q2W`/`NRS` 不被拉开
- NRS 两行三列对齐原文
- 表3 邻行不叠字；Dose 列为 `Q2W`/`Q4W`
