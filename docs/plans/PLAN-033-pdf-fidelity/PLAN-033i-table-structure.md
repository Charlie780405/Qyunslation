# PLAN-033i：表格结构化

> 状态：**已完成**（033n / WT-033n 已关）
> 父计划：[PLAN-033](./PLAN-033-pdf-fidelity.md)
> 验收门：`bash scripts/verify-plan-033i.sh`
> 前置：033g

## 目标

识别表题、表头、分组行、行列、单元格和表格脚注，生成旋转无关的稳定单元格块 ID。计数正确不再被当成表格完成。

## 根因

033b 只补了区域几何。`TableObject.planned_action` 仍是 `text_layer`，`reconstructed=False`。BabelDOC RapidOCR table adapter 已退役/no-op，不能当执行器。旋转整页表和缺网格表没有局部坐标系。

## 实现边界

改：

- `qyunslation/structure/tables.py`：旋转无关局部坐标；组合文字 span、横竖线、间距聚类
- 缺文字层时**仅对表格区域** ≥300 DPI OCR
- 为每个单元格写入稳定 `block_id` + `role` + 行列/跨行跨列
- 明确角色：`table_title | table_header | table_group | table_cell | table_footnote`

不改：

- 不调用已退役 RapidOCR table adapter
- 不把整张表栅格化
- 不在本子计划做 LLM 翻译与续页（033j）

## 失败策略

| 情况 | 动作 |
| --- | --- |
| 有表题但圈不到行列 | `TABLE_STRUCTURE_INCOMPLETE`，不得假装完成 |
| 旋转页用页坐标错位 | 必须先建局部坐标 |
| 只有部分文字层 | 表区 OCR 补洞，禁止整页 OCR |

## 验收

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | 合成网格表产出稳定 cell block_id | 通过 |
| V2 | 旋转 90° 整页表局部坐标正确 | 通过 |
| V3 | 缺完整网格仍能聚类出行列 | 通过 |
| V4 | 表题/表头/分组行/脚注角色可区分 | 通过 |
| V5 | 不引用 RapidOCR table adapter | 通过 |
| V6 | `verify-plan-033i.sh` | `SUMMARY: PASS fail=0` |
