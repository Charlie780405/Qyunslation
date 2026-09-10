# 踩坑（SK-Q003）

1. PDF 抽出的空白格若当非空，会误送翻译或报 `MISSING_TARGET`。空源必须 `PRESERVE`。
2. 换行测试用无空格中文不会走 `wrap_lines`；要用英文词列才能触发折行。
3. 把 `FONT_BELOW_TARGET` 塞进共享 `HARD_FAIL` 会让图片路径误失败；表格用 `TABLE_HARD_FAIL`。
