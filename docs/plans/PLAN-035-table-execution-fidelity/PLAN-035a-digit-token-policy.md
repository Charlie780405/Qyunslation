# PLAN-035a：数字 token policy SSOT

> 状态：**实施中**

## 交付

- [`qyunslation/structure/table_cell_policy.py`](../../../qyunslation/structure/table_cell_policy.py)
- [`StructuredTableCell.as_block()`](../../../qyunslation/structure/table_structure.py) 写入 `translation_policy`
- `PDF_STRUCTURE_SCANNER_VERSION` → `1.7.0`

## 规则

- `PRESERVE`：整格纯数值/占位
- `PROTECT_TOKENS`：含受 protect 覆盖的 token
- `TRANSLATE`：其余
