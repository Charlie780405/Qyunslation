# PLAN-041d：完整性与版式硬门禁

> 状态：**已完成**
> 父计划：[PLAN-041](./PLAN-041-pdf-regulatory-form-fidelity.md)

## 实施

1. `qyunslation/structure/table_qc.py` 输出逐格 QC：政策、源/目标语种、保护 token、字号、粗体、溢出、换行、回写结果。
2. `TRANSLATE` 中文残留 → `SOURCE_RESIDUE`；空译文 → `MISSING_TARGET`；`PRESERVE` 空格允许。
3. `FONT_BELOW_TARGET` 只进表格链；图片仍走 `HARD_FAIL`。
4. `translate_pdf_tables`：fit 硬错误先于 redaction；失败不写 `.tbltr.pdf`；`terminal_success=false`。
5. 缺 `QYUNSLATION_PLAN041_SAMPLE` 时 `verify-plan-041.sh` 输出 `BLOCKED` 并非零退出。

## 验收

- 正文不低于 `max(7pt, 70% 源字号)`，脚注不低于 5.5pt。
- 硬错误不落半成品。
- 7 页实样无 LLM：14 表逐格账本，空源格均为 `PRESERVE`。
