# ADR-030：PDF 三线表单元格提取选型

> 日期：2026-09-10  
> 状态：**已接受**  
> 关联：[PLAN-030-table](../plans/PLAN-030-semantic-layout-translation/PLAN-030-table-pdf-cell-reconstruction.md)

## 背景

030d 已用题注 + 横线群实现 **6/6 表格区域保护**。单元格级审计需要 `row_count`/`column_count` 与 `translatable_blocks` 按 cell 对齐。

## 候选评估（Task 0）

| 候选 | 结果 | 原因 |
| --- | --- | --- |
| PyMuPDF `find_tables()` | 否决 | 030d 已证：召回低、列数错、假阳性（不复用） |
| **camelot-py** | 未采纳 | 生产 venv 无 pip 便捷安装链；opencv 与现有栈冲突风险；金样已被 033i 自研路径覆盖 |
| **tabula-py** | 未采纳 | 本机 **无 Java**；CI/部署需额外 JRE |
| **in-house `table_structure.py`（033i）** | **采纳** | 旋转局部坐标 + 横/竖线聚类 + 文本桶；ljae439/Nature 6 表全绿 |

Task 0 证据：`python scripts/spike-plan030-table-task0.py` → `/tmp/plan030-table-task0.json`

## 决策

1. **不引入** camelot/tabula 生产依赖。
2. **延续并收口** `qyunslation/structure/table_structure.py` 为 PDF 单元格 SSOT。
3. `scan_pdf.py` 写入 `TableObject.row_count` / `column_count`（由 `table_grid_dimensions()` 派生）。
4. 执行侧数字保护沿用 033i `table_translate` / `TranslationPolicy` 既有逻辑。

## 后果

- 正面：零新系统依赖；与 030d 区域保护同栈；030h 跨格式对账可比对 DOCX `row_count`。
- 负面：极弱线框 / 纯图片表仍可能只有区域保护；跨页续表仍 out of scope。
