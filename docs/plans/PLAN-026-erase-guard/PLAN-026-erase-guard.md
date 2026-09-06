# PLAN-026 擦除保护与竖向锚定复位

## 目标

修复实心填充抹掉相邻图元、以及白底标签整体上移的问题；把 SK-Q002 重构为可迁移规范（通用原则 + 新图自检清单）。

## Out of Scope

- 不改 OCR 引擎选型与 LLM 翻译链路
- 不改 Gradio 布局 / viewer（024 已修）
- 不处理非图片链路（PDF/DOCX）

## 根因

1. 纯色分支对整 OCR 框 `cv2.rectangle` 填充；OCR 框比文字带宽，框顶/底蹭到的括号线、色带被白填抹掉。
2. 白底从「墨迹中心对齐」改成「顶对齐」后，渲染块矮于原文墨迹时视觉中心上移 `(H_src-H_dst)/2`（样例约 10.5px）。

## 方案

1. `_fill_band`：填充收敛到非线状文字行带 ±pad
2. `_line_guard_mask`：贯穿线图元保护；擦后回贴文字带外原图像素
3. 竖向三段式 + `anchors.vertical_mode`；C8 按该字段度量
4. QC C10：文字带外图元损伤
5. SK-Q002：通用原则 + 新图自检清单；pitfalls/reference/registry 同步

## 验收

`bash scripts/verify-plan-026.sh`：括号线存活 ≥90%；周数中心偏移 ≤3px；无 C8/C9/C10；回归 025。
