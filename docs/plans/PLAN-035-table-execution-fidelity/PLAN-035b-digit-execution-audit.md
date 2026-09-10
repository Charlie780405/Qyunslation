# PLAN-035b：执行断言与 manifest 回写

> 状态：**实施中**

## 交付

- [`translate_table_blocks()`](../../../qyunslation/structure/table_translate.py)：按 policy 分流；`assert_digit_tokens_preserved`
- [`pdf_table_translate.py`](../../../scripts/pdf_table_translate.py)：`output_evidence.checks.digits_preserved`
