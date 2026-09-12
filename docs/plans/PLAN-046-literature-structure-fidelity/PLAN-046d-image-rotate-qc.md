# PLAN-046d：插图旋转与质检

> 状态：已完成
> 父计划：[PLAN-046](./PLAN-046-literature-structure-fidelity.md)

## 交付

1. 竖排轴标签：短边估字号 + 水平绘制后 `rotate(90)` 贴回；`ROTATED_TIER`。
2. 面板字母识别 `(a)` / OCR 易混 `8→B`。
3. `_is_ocr_garbage`（如 `F08`）不擦不画。
4. C6 警告汇入 `object_qc`。

## 验收

- `tests/extensions/test_plan046d_rotate.py`
