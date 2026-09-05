# PLAN-008c：样例模板

- `scripts/doc_profiles.toml`：letter / literature / regulatory / generic
- `scripts/doc_profile.py`：`load` / `detect` / `apply` / `patch_line_skip`
- `ocr_pdf_with_hpd(..., aggressive=, min_font_size=)`

`detect` 只读本地 PDF 文字层或文件名，不请求泰州 HPD。
