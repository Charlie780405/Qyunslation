# PLAN-049g：HPD 补列 + 统一字体 + 三线补全

> 状态：已实现
> 父计划：[PLAN-049](./PLAN-049-literature-table-leave-babeldoc.md)

## §0 上一子计划缺口

WT-049 遗留：表头 `(N=130)` 碎段；V6 重译手测。用户新反馈（049f 之后）：

| 缺口 | 归并 |
| --- | --- |
| 表1 底线缺右段（原文 74.8–514.8，译文止于 ~437） | 本计划：原文横线重描 |
| 译文 SourceHan / Univers / STIX / china-s / helv 混用；表3 子集缺字 | 本计划：NotoSansSC 一族 |
| 表3 列未对齐（空隙投影并列） | 本计划：HPD 7 列优先 |

## 目标

不整区 `paint_fitted_blocks`。HPD 只补**列几何**；横线从原文 drawings 补全；表内落笔改 NotoSansSC（含半角拉丁），不再混 `china-s`/`helv`。

## Out of Scope

- 整区擦除重画；HPD OCR 进译文
- 换模型；Office 建表；监管表单
- 表头碎段 `(N=130)` 语义重建

## 交付

1. `hpd_column_ranges` / `resolve_column_ranges`：有原文三线才调 HPD；列数 ≥ 空隙则用 HPD
2. `restore_rule_lines`：按原文表区横线在译文重描（补表1 底线）
3. 落笔与剩余 span 统一 `QYUNSLATION_FONT`（NotoSansSC）；`normalize_ascii` 仍做
4. SK-Q009 铁律 H/I 修订 + J；verify / WT

## 判据

- 原文有底线则译文同 y 带有等宽横线
- 表3 HPD 可达时列数=7；数据 token 落入对应列中带
- 后处理落笔 fontname 为 `qy-tbl` / Noto，表内无新的 china-s/helv 混排
