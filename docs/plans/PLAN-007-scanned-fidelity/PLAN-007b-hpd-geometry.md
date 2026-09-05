# PLAN-007b：HPD 隐形层几何与字号

## Task B1 — 调试转储

`QYUNSLATION_HPD_DEBUG=1` → `<dest>.hpd-debug.json`（原始坐标、缩放 box、字号、y 覆盖率）。

## Task B2 — 坐标映射

按轴独立归一化；box 越界或覆盖率异常则 warning + 退回像素映射。

## Task B3 — 换行感知字号

`_fit_fontsize` 二分；下限 7.0、上限 28.0；盒高不足优先向下扩展（受下一块 y1 限制）。

## Task B4 — 回归

- `insert_textbox` 溢出记 warning
- `test_hpd_ocr_smoke.py`：字号中位数 ≥ 8pt

## 验收

- smoke 全绿
- 第 1 页 OCR 字号中位数 ≥ 9pt、最小 ≥ 7pt

## 回滚

`git revert`；`hpd_ocr.py` 无状态。
