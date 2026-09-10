# PLAN-038b：PLAN-037 补档（不改行为）

> 状态：**已完成**
> 父计划：[PLAN-038](./PLAN-038-gap-closure.md)
> 归属缺口：G-DOC-008
> 验收：WT-037 / `bash scripts/verify-plan-037-table-observability.sh`

## 交付

1. [`../PLAN-037-table-observability/PLAN-037-table-observability.md`](../PLAN-037-table-observability/PLAN-037-table-observability.md)
2. [`../../walkthroughs/WT-037-table-observability.md`](../../walkthroughs/WT-037-table-observability.md)
3. WT-036「037」节改为详见 WT-037

## 非目标

- 不改 `table_execution_observability` / `pptx_table_exec` 行为
- 不重写 `verify-plan-037-table-observability.sh`

## 验收

- `bash scripts/verify-plan-037-table-observability.sh` PASS
- registry `G-DOC-008` = closed
