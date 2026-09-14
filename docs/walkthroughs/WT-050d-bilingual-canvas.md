# WT-050d：原译文双画布

对应 [PLAN-050d](../plans/PLAN-050-qyunslation-ui-ux/PLAN-050d-bilingual-canvas.md)

- 主视图仍是 `.qy-preview-src` / `.qy-preview-dst`（PLAN-017 + 021 viewer）
- 窄屏：`body.qy-050-src-only` / `qy-050-dst-only`；Alt+1 / Alt+2 切换
- 页定位：检查器页码 + `qy050:goto-page`；百分比滚动只作降级
- 高清/缩放/旋转沿用 `apply-pdf2zh-viewer.py` / `preview-dpi`
- 原文画布无编辑控件（只读）
