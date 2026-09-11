# PLAN-043c：表格链成功交付

> 状态：已完成
> 父计划：[PLAN-043](./PLAN-043-regulatory-form-label-leakage.md)
> 优先级：**P1**（结构性正解；与「文字版长句 OK」并行）

## 背景

611-2期 **12 表已检出**，但生产 job **无 `.tbltr.pdf`**。漏译标签在扫描上属于表格单元格，正确专路是 041 单元格链而非段落回退。

## 611-2期 probe 硬失败码（2026-09-11）

| 表 | 页 | 硬失败码 |
| --- | --- | --- |
| table:page:1:anonymous:1 | 1 | `FONT_BELOW_TARGET`, `SOURCE_RESIDUE` |
| table:page:1:anonymous:2 | 1 | `TABLE_DIGIT_DRIFT` (r2c1 药物名 OCR 乱序含 611) |
| table:page:1:anonymous:3 | 1 | `TABLE_DIGIT_DRIFT` |
| table:page:1:anonymous:4 | 1 | `TABLE_DIGIT_DRIFT` |
| P2–P5 其余 8 表 | 2–5 | 以 `TABLE_DIGIT_DRIFT` / `SOURCE_RESIDUE` 为主 |

## 交付

1. 对每类 QC 做**最小误杀修复**（延续 WT-042：`3SBio` 受控跳过 DIGIT_DRIFT、`normalize_phase_label` 不吞长标题、`CELL_MERGE` 收紧）。
2. `PROTECT_TOKENS` 格（含 611、CTR 号）译后 digit token 审计放宽或走 preserve。
3. 生产路径 `translate_pdf_tables` 成功后写出 `.tbltr.pdf`。

## 验收

- 611-2期 EN mono 同目录存在 `*.tbltr.pdf`。
- 或 WT-043 列明仍未关闭的 QC 码 + 后续 PLAN 编号（不得静默伪成功）。

## 非目标

- 本阶段不要求 P1 标签**仅**来自表格链（043a/b 段落直替仍作回退保险）。
