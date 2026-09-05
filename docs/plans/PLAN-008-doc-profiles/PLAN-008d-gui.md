# PLAN-008d：GUI 下拉

`scripts/apply-pdf2zh-docprofile.py` 幂等补丁：

- 下拉：自动 / 正式书信 / 学术文献 / IND递交资料 / 通用
- 上传后若仍为「自动」，显示 `自动（识别为：正式书信）`
- `_run_translation_task` 先 `apply` + `patch_line_skip`，再把 `aggressive`/`min_font_size` 传给本地 `hpd_ocr`

`pdf2zh.service` ExecStartPre 追加该脚本。
