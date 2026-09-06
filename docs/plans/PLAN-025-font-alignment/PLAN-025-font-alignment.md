# PLAN-025 译文对齐锚定原图墨迹

## 背景

PLAN-024 字号层级已通过；用户反馈「没有做与原图相应的文字横竖对齐」。

## 根因

渲染把 `_available_box`（最宽可扩到 OCR 3 倍）当排版框居中，而 `align` 在 OCR 框内计算，基准不一致。参考图 60 框中 50 框偏移 >12px：竖向统一下沉 16–20px，横向最多右移 1125px。

## 改法

1. `_ink_geometry`：Otsu 墨迹 bbox + y 投影切行
2. `_infer_align`：行间 x1/cx/x2 标准差；实心强制 center
3. 排版锚主行墨迹；实心垂直居中 / 非实心顶对齐向下生长
4. 居中仅钳图像边界；可用区只做换行宽
5. QC C8：成品 vs `draw_bbox` 计划锚点，`ALIGN_TOL_PX` 默认 12（吸收字形/Otsu 测量噪声）

## 验收

`scripts/verify-plan-025.sh`：源码断言 + 参考图中英互译 + 回归 PLAN-024。
