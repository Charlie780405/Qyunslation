# WT-036：表格数字 policy 跨格式统一与续表金样

日期：2026-09-10  
纲领：[PLAN-036](../plans/PLAN-036-table-policy-unification/PLAN-036-table-policy-unification.md)

## 交付摘要

| 子计划 | 交付 |
| --- | --- |
| 036a | `table_cell_policy.is_numeric_or_unit`；`md_tables` / `doc_image_policy` delegate SSOT |
| 036b | `scan_docx` 表格块 `translation_policy` + `BlockRole.TABLE_CELL` |
| 036c | `reference/cai-2025-table1-continued.pdf` + truth JSON + 金样 scan 断言 |
| 036d | `verify-plan-036.sh`；`verify-release.sh` 增加 036 门 |

## 金样

| 项 | 值 |
| --- | --- |
| 文件 | `tests/fixtures/structure/reference/cai-2025-table1-continued.pdf` |
| SHA256 | `b5ec069391306f5a1dd3155ae60ba5c25e3205d8b74ac4a617d3214158ebb0a8` |
| 格式 | Wiley `TABLE 1 \| (Continued)` |
| 预扫 | `summary.table_count=1`，`table:1` occurrence ≥ 2 |

## 验收

```bash
QYUNSLATION_VERIFY_PY=/home/dev/qyunslation/.venv/bin/python bash scripts/verify-plan-036.sh
QYUNSLATION_VERIFY_PY=/home/dev/qyunslation/.venv/bin/python bash scripts/verify-release.sh
```

## 遗留

- Tailoring 型 `Table N continued`（窄空格、无 `\| (Continued)`）仍不解析
- DOCX 执行器消费 `translation_policy`（manifest 已对齐，执行路径待后续）
- PPT 表格 policy 未纳入
