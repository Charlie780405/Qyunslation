# PLAN-046：文献 PDF 结构保真整改

> 状态：**已实现**（须重译验收）
> 日期：2026-09-11
> 前置：[PLAN-045](../PLAN-045-literature-pdf-fidelity/)
> 原则：结构不可信就不落笔；占位符闭环
> 验收：`bash scripts/verify-plan-046.sh`；证据 [WT-046](../../walkthroughs/WT-046-literature-structure-fidelity.md)

## 目标

止住「越改越差」：摘要串行、表格列切碎截断、图内竖排巨字/白块、质检全绿。不换模型，不改原文，不重开 PLAN-044 监管软门。

## MathTranslate 取舍

不照搬 LaTeX 重编译。只取：结构不可信不落笔；受保护 token 译后校验。

## 子计划

| ID | 交付 |
| --- | --- |
| [046a](./PLAN-046a-stop-bleed-gates.md) | 门禁止血：isolate 复原、COLUMN_CLUSTER_DRIFT、字号上限、先试排后擦 |
| [046b](./PLAN-046b-paragraph-merge.md) | 摘要段落再合并 + min_scale=0.8 + 药名漂移告警 |
| [046c](./PLAN-046c-table-columns.md) | 列簇二次合并 + 墨迹并集 bbox + SPAN_ORDER_DRIFT |
| [046d](./PLAN-046d-image-rotate-qc.md) | 竖排旋转绘制 + 面板字母放宽 + OCR 垃圾 + object_qc |
| [046e](./PLAN-046e-verify-docs.md) | verify / WT / 服务重启 |

## 实样

`QYUNSLATION_PLAN045_SAMPLE`（ljae439 / ECZTRA，仓库外）。
