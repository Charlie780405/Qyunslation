# PLAN-049h：HPD 格为落笔单元（表头 + 字号）

> 状态：已实现
> 父计划：[PLAN-049](./PLAN-049-literature-table-leave-babeldoc.md)

## §0 核心逻辑（049g 之后仍错的原因）

049g 只做了「有 7 条 x 带 + 改数据行数字」。**表没有在 HPD 格上成形。**

实测 `6ab18daa` / HPD 表3：

| 层 | 事实 |
| --- | --- |
| HPD | 7 列：Dose / Visit / ADA / nAb / 浓度 / IGA / EASI |
| 数据行 `_assign` | `第52周` 与 `安全性随访` 已在同一 Visit 列（col1） |
| 表头 dest | `剂量ADA anAb 访视…` 仍在 x≈68–156（BabelDOC 段流） |
| `unify_region_font` | 原位换 Noto，**锁死错误 x** → 表头重叠、ADA/nAb 挤前 |
| DLQI | dest 一行 `16.0(7.6), N=128`，字号取 dest 中位 6.8（BabelDOC 已压到 3.5–6.8）；`_place_x` 再缩 |

用户看到的「两列 Visit / 浓度与 IGA 混列」是**表头几何与数据列错位**，不是 HPD 少一列。

## 目标

HPD **格**（行×列）才是落笔单元：表头按格写，不再原位 restyle；格内溢出换行，不把字号压到低于表体。

## Out of Scope

- 整区 `paint_fitted_blocks`；HPD OCR 进译文
- 换模型；表头 `(N=130)` 语义重建
- 监管表单

## 交付

1. 表头行：关键词从 dest 段流舀入 7 槽，按 origin 表头两行写入对应列
2. 禁止对表头做 `unify_region_font` 原位锁 x
3. 字号用 origin 表体（≥7.2pt）；`16.0 (7.6), N=128` 在格内拆成两行，禁止再缩
4. Visit 角色锁：`第N周`/`安全性随访` 只能进 origin 为 Week/Safety/Visit 的列

## 判据

- 表3 表头：剂量 / 访视 / ADA / nAb / 浓度 / IGA / EASI 各在其列中带
- 数据行 Visit 仅一列；浓度 x 中心 ≠ IGA x 中心
- DLQI 数值行字号 ≥ 邻行 × 0.85
