# PLAN-033b：表格几何补强

> 状态：**已完成**（`verify-plan-033b.sh` PASS）
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 前置：033a（11 页样本仍有 `TABLE_GEOMETRY_MISSING`）
> 验收门：`bash scripts/verify-plan-033b.sh`

## 根因

`table_regions` 只从题注**向下**收横线群，且相邻横线间距超过页高 20% 就断开。

11 页样本第 5 页 Table 1 是侧放整页框线表：题注在框左侧，只有顶/底两条长横线和左右竖框。两条横线相距约 0.90 页高，旧算法圈不定，对象 bbox 退化成题注细条。Table 2–4 已有横线群，不改。

## 做法

在现有 `tables.py` 上补封闭框回退：两横 + 两竖围成矩形，且与题注相邻（左/右/上/下或重叠）。无题注的页仍然返回空，不换库、不做单元格重建。

扫描器版本 `1.2.0` → `1.3.0`，旧缓存失效。TableObject 有区域时用区域 bbox，不再只用题注框。

## 不改

- Camelot / Java / `find_tables()`
- 030h D1–D5、033c 补丁、参考文献、预览 DPI

## 验收

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | 合成 `landscape-frame-table.pdf` 圈定 table 1 | 通过 |
| V2 | Nature / ljae 原金样区域不变，无 `TABLE_GEOMETRY_MISSING` | 通过 |
| V3 | 无横线的「Table 1 + 正文」仍记 `TABLE_GEOMETRY_MISSING` | 通过 |
| V4 | 11 页样本在场时四表都有 `table_rule_lines` 证据 | 通过或 skip |
