# 踩坑（SK-Q003）

1. PDF 抽出的空白格若当非空，会误送翻译或报 `MISSING_TARGET`。空源必须 `PRESERVE`。
2. 换行测试用无空格中文不会走 `wrap_lines`；要用英文词列才能触发折行。
3. 把 `FONT_BELOW_TARGET` 塞进共享 `HARD_FAIL` 会让图片路径误失败；表格用 `TABLE_HARD_FAIL`。
4. **不要**裸降 `min_text_length` 修短标签漏译——会让 1–4 字碎片涌入 LLM，冲击 003/004；用 form 层直替（042b）。
5. 表格链硬失败若 GUI 无「N 个表格未保真」提示，检查 `apply-pdf2zh-docimg` 是否注入了 `execution_table_fidelity_hint`（042f）。
6. `II 期` 被抽成 `11 期` 时走 `normalize_phase_label`，勿当阿拉伯数字翻译。
