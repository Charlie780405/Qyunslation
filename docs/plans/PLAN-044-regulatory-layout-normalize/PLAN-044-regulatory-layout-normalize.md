# PLAN-044：监管表单译文版式归一化与交付率收口

> 状态：**已实现**（代码/门禁；实样 EN 重译待验收）
> 日期：2026-09-11
> 前置：[PLAN-041](../PLAN-041-pdf-regulatory-form-fidelity/)、[PLAN-042](../PLAN-042-regulatory-translation-quality/)、[PLAN-043](../PLAN-043-regulatory-form-label-leakage/)
> Skill：[SK-Q003](../../../.cursor/skills/pdf-regulatory-form-fidelity/SKILL.md)
> 验收：`bash scripts/verify-plan-044.sh`；证据 [WT-044](../../walkthroughs/WT-044-regulatory-layout-normalize.md)

## 问题结论

用户所见「排版混乱 / 字体不统一 / 短词漏译 / 断行压线」是**漏译触发整表回退**的末端表现，不是独立排版 bug。

实样（job `fd3b740e`，611 III 期）：14 表 / 492 格；表格链仅画 10 格；13/14 `FAILED_HARD`，主因 `SOURCE_RESIDUE`；输出并存 NotoSans + SimSun + Calibri，字号 14 档。

## 根因四层

| 层 | 根因 | 修复 |
| --- | --- | --- |
| H | `_vector_grid_cells` 裸 y0 排序 + `" ".join` | 044a 行分桶 / CJK 零空格 / 软换行 |
| A | `_llm_translator` 源文静默透传 | 044b 缺索引单条补译，禁止伪译文 |
| G | `SOURCE_RESIDUE`∈表级终止 | 044c 格级降级；残留率 >30% 才终止；REGULATORY 专属 |
| B | 源字号 tier + 双重 shrink + inset 0.6pt | 044d 表级字号阶梯 / 真实字宽 / role-aware inset |

## 决策

- 未译中文格：保留原文，仍 `paint_cell` 重绘为 NotoSansSC + 统一字号
- 表格链优先隔离策略：仅 `ContentProfile.REGULATORY`

## 子计划

| ID | 交付 |
| --- | --- |
| 044a | `compose_cell_text` / `join_span_texts` |
| 044b | `scripts/pdf_table_translate.py` 批内补译 |
| 044c | `TABLE_CELL_DEGRADED` + `RESIDUE_RATE_LIMIT` |
| 044d | `TABLE_ROLE_SIZE` + `measure_textbox` + paint inset |
| 044e | verify / SK-Q003 / 错误台账 H 族 / WT-044 |

## 量化门（实样，经 `QYUNSLATION_PLAN044_SAMPLE`）

- 表格链交付格 ≥ 450/492；`FAILED_HARD` ≤ 1/14
- 残留中文格 ≤ 25；表内字体族 = 1；字号档 ≤ 4；`<7pt` ≤ 10%
