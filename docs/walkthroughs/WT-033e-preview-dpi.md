# WT-033e 当前页 300 DPI 与语义进度

> 计划：[PLAN-033e](../plans/PLAN-033-pdf-fidelity/PLAN-033e-preview-dpi.md)
> 日期：2026-09-09
> 验收门：`bash scripts/verify-plan-033e.sh` → `SUMMARY: PASS fail=0`

## 做了什么

`pdf_preview_pages.render_preview_pages` 只把当前页打到 300 DPI，其余 72 DPI。GUI 补丁记下当前页并标 `data-qy-preview-dpi=300`。进度文案 `已处理 图 x/n · 表 y/m`，docimg 后处理用 manifest 图/表计数，不再只报 OCR 步。

## 验证

| # | 结果 |
| --- | --- |
| V1 非当前页不是 300 DPI | 通过 |
| V2 当前页长边 = 页 pt × 300/72 | 通过 |
| V3 进度分母为 figure+table | 通过 |

## 部署

已合 `main`（`f83c5ff`）。GUI 有 `_qy_preview_dpi` / `format_from_manifest`，无 `file_path = _qy_new`。`pdf2zh.service` 23 条 ExecStartPre，`:7860` 200。
