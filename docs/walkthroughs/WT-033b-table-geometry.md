# WT-033b 侧放框线表几何

> 计划：[PLAN-033b](../plans/PLAN-033-pdf-fidelity/PLAN-033b-table-geometry.md)
> 日期：2026-09-09
> 验收门：`bash scripts/verify-plan-033b.sh` → `SUMMARY: PASS fail=0`

## 做了什么

11 页样本第 5 页 Table 1 是侧放整页框线表：题注在左侧，只有顶/底横线和左右竖框。旧算法只向下收横线群，两条横线相距约 0.90 页高，整表失踪，bbox 退化成题注细条。

在 `tables.py` 补封闭框回退（两横 + 两竖，且与题注相邻）。无题注的页仍返回空。TableObject 有区域时用区域 bbox。扫描器 `1.2.0` → `1.3.0`。

仓内合成夹具 `landscape-frame-table.pdf` 是主门。Elsevier PDF 不入库。

## 验证

| # | 结果 |
| --- | --- |
| V1 合成框线表圈定 table 1 | 通过 |
| V2 Nature / ljae 无 `TABLE_GEOMETRY_MISSING` | 通过 |
| V3 无横线 Table 1 仍记 WARNING | 通过 |
| V4 11 页样本四表都有 `table_rule_lines` | 通过（本机样本在场） |

## 未做

033d（参考文献口径）、033e（300 DPI 预览）。033f 总门已立。
