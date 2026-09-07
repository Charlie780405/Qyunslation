# PLAN-029a 期刊类 Markdown 表管道

## 目标

NEJM/Springer 期刊 PDF 导出 `.zh.md` 时，将 `table_status == "ok"` 的表体替换为翻译后的 Markdown 管道表。

## 实现

### `scripts/md_tables.py`

- 跨仓复用 [`lit_tables.py`](/home/dev/Hermes/scripts/lit_tables.py)：`extract_tables_pdf`、`rows_to_markdown`、`trim_glued_rows`
- `inject_translated_tables(md_text, src_pdf)` 对外 API
- 幻灯 PDF（首页 `is_slide_page`）直接跳过
- 只注入 `ok` 表；`pending`/`unstructured` 静默跳过
- 非数值单元格经 `letter_translate_prompt.translate_blocks` 批量翻译
- Springer 题注 `Table N | Title` 格式：`caption_anchor` 不认 `|`，增加 `_PIPE_CAPTION` 回退匹配

### `scripts/export_md_docx.py`

- `_maybe_inject_tables` 包装，异常降级
- debug json 路径与 ConverterHpd 路径均在写盘前调用

## 验收

- ok 表注入后含 `| --- |`
- 原数值字符串零改写
- pending/unstructured 不产生注入痕迹
