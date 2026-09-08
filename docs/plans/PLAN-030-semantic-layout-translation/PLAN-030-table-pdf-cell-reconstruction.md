# PLAN-030-table 子计划：PDF 三线表单元格级重建

**状态**：待批准（技术选型门）  
**类型**：横切能力（PDF 专用，不阻塞 030f/030g 主链）  
**依赖**：PLAN-030d Task 8 区域保护已交付；WT-030d 已记录 `find_tables()` 失败证据  
**与主链关系**：可与 PLAN-030f 并行立项；**实施建议排在 030g 之后、030h 之前**（避免同时动 PDF 表与 PPT 嵌图）

## 一、问题

学术 PDF 常见**三线表**（仅横线、无竖线）。030d 已交付：

- 题注 + 横线聚类的**表格区域保护**（6/6 金样、零假阳性）
- `TableObject.row_count/column_count` 在 PDF 侧**恒为 None**
- `ManifestIssue(TABLE_GEOMETRY_MISSING)` 对 Nature p5 等页留痕

用户目标（纲领 §3.1）要求：表头/文本单元格可译，**数字与单位 token 不变**。区域保护 alone 无法满足单元格级审计与数字保护断言。

## 二、030d 已否决路线（不复用）

| 方案 | 结论 | 证据 |
| --- | --- | --- |
| PyMuPDF `find_tables()` | 否决 | ljae439/Nature 召回低、列数错、假阳性 |
| `strategy="text"` | 否决 | 拦腰切断数值行 |
| 030d 原位 PDF 重建 | 范围降级 | 无可靠 cell grid |

## 三、候选技术栈（选型门 Task 0）

| 候选 | 系统依赖 | 优势 | 风险 |
| --- | --- | --- | --- |
| **camelot-py**（pdfium 后端） | opencv-headless；默认不需 ghostscript | 学术表常用；纯 Python wheel | 与现有 `opencv-python` 可能冲突 |
| **tabula-py** | **Java 8+** | 表格线弱时有时更好 | 本机无 Java；CI 需 JRE |
| **pymupdf4llm + layout** | 非开源 layout 许可 | 与 PyMuPDF 同栈 | 额外许可与版本钉扎 |

**Task 0 交付**：在 ljae439 + Nature 6 表上跑 spike 脚本，输出 recall/列数/数字 cell 完整性矩阵 + 选型 ADR。**未过选型门不得写生产路径。**

## 四、目标架构（选型通过后）

```text
table_regions() [030d 已有]
    → cell_grid_extractor (新)
    → TableObject.row_count/column_count + translatable_blocks[] per cell
    → execution: 数字 cell EXPLICITLY_SKIPPED / token 校验
    → output_evidence.checks.digits_preserved
```

与 DOCX 030e 单元格模型对齐，便于 030h 跨格式对账。

## 五、任务草案（选型后细化）

1. **Task 0**：spike + ADR（1–2 天）
2. **Task 1**：依赖与环境（camelot **或** tabula+Java；写入 `pyproject.toml` optional group）
3. **Task 2**：`pdf_table_cells.py`：区域保护 bbox 内提取 cell grid
4. **Task 3**：`scan_pdf.py` 填充 `row_count`/`column_count`/cell blocks
5. **Task 4**：执行侧数字 token 保护断言 + manifest 回写
6. **Task 5**：金样 6 表 + `verify-plan-030-table.sh`

## 六、完成定义

- ljae439 + Nature 全部 Table 有非空 `row_count`/`column_count`
- 数字单元格译后 token 集合不变（自动化）
- 030d 区域保护回归不退化
- Nature p5 `TABLE_GEOMETRY_MISSING` 收敛为 0 或降级为已知 WARN

## 七、非目标

- DOCX 表格（030e 已单元格级）
- 跨页续表合并
- Markdown 抽表替代 PDF 原位
