# PLAN-035c：跨页续表扫描

> 状态：**已完成**（PLAN-035 / WT-035）

## 交付

- [`continued_table_anchors()`](../../../qyunslation/structure/captions.py)
- [`scan_pdf.py`](../../../qyunslation/structure/scan_pdf.py)：多 occurrence + row 全局化
- 合成夹具 `continued-table.pdf`（[`generate_synthetic.py`](../../../tests/fixtures/structure/generate_synthetic.py)）
