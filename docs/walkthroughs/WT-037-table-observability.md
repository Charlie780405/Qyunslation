# WT-037：表格执行可观测 + PPT policy 执行

日期：2026-09-10  
纲领：[PLAN-037](../plans/PLAN-037-table-observability/PLAN-037-table-observability.md)  
补档来源：[PLAN-038b](../plans/PLAN-038-gap-closure/PLAN-038b-plan037-docs.md)（功能早于文档）

## 交付摘要

| 项 | 交付 |
| --- | --- |
| P1-A | `table_execution_observability`；预扫摘要 + manifest API + tbltr 后进度展示 |
| P1-B | `pptx_table_exec` + `PPTXTranslator` 按 policy 分流 |
| merge | `a4b61a8`（见 WT-036 部署记录） |

## 验收

```bash
QYUNSLATION_VERIFY_PY=/home/dev/qyunslation/.venv/bin/python \
  bash scripts/verify-plan-037-table-observability.sh
```

## 关闭缺口

`G-DOC-008`（038b）
