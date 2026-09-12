# PLAN-048d 左边界与降级

- `tables._expand_region_left` 纳入被切左列
- 降级：HPD 落笔 → NOT_A_TABLE 交图片 → 失败 normalize → gutter → 只归一
- `pdf_table_translate` 部分成功时仍对失败表 normalize
