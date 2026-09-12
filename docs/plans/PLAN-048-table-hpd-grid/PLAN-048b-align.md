# PLAN-048b 行几何 × 列 HPD 对齐

- `structure_table_ex`：HPD → gutter → geometry_center
- `align_hpd_grid` 左到右前缀匹配
- 删除 `_merge_column_clusters` 有效合并（保留空操作兼容）
- bbox 取真实墨迹并集
