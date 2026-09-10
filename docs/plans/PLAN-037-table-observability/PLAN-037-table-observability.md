# PLAN-037：表格执行可观测 + PPT policy 执行

> 状态：**已完成**（功能在 036 收口时已合入；本文件为 038b 补档）
> 日期：2026-09-10
> 验收：[WT-037](../../walkthroughs/WT-037-table-observability.md) / `bash scripts/verify-plan-037-table-observability.sh`
> 前置：PLAN-035 / PLAN-036
> 来源：WT-036 §037 P1-A/P1-B；缺口 `G-DOC-008`

## 目标

1. **P1-A**：扫描/执行期表格保真信号可观测（`TABLE_DIGIT_DRIFT`、`digits_preserved`、`TABLE_CONTINUATION_UNLINKED` 等）进入预扫摘要、manifest API、tbltr 后进度文案。
2. **P1-B**：PPTX 表格单元格按 `translation_policy` 分流（对齐 DOCX/`table_cell_policy`）。

## 交付（已存在，不改行为）

| 模块 | 路径 |
| --- | --- |
| 可观测 | [`qyunslation/structure/table_execution_observability.py`](../../../qyunslation/structure/table_execution_observability.py) |
| PPT 执行 | [`qyunslation/structure/pptx_table_exec.py`](../../../qyunslation/structure/pptx_table_exec.py) |
| 门禁 | [`scripts/verify-plan-037-table-observability.sh`](../../../scripts/verify-plan-037-table-observability.sh) |
| 测试 | `tests/structure/test_table_execution_observability.py`、`test_plan037_pptx_table_exec.py` |

## 非目标

- 纯图片表 / PPT picture OCR → PLAN-038d / 038e
- 重写 035/036 policy SSOT

## 完成定义

- 本纲领与 WT-037 存在且指向上述门禁
- `verify-plan-037-table-observability.sh` PASS（已纳入 `verify-release.sh`）
