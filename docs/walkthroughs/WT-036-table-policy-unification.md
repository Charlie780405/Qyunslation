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
| 036e | Tailoring 续表题注；DOCX 执行器消费 policy；PPT 表格 policy |

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

## 部署

| 项 | 值 |
| --- | --- |
| merge | `ab01544`（036e → `origin/main`） |
| 服务 | `pdf2zh.service`、`qyunslation-office.service` → active |
| verify-plan-036 | PASS（036e 部署后复验） |
| verify-release | 030i/035/036/030-table PASS；033l 可无样本 BLOCKED |

## 036e 补充（遗留收口）

| 项 | 交付 |
| --- | --- |
| 续表题注 | `continued_table_caption_num`；Tailoring `Table 1  continued` 可解析 |
| DOCX 执行 | `docx_table_exec.partition_docx_segments`；`DocxTranslator` 跳过 PRESERVE、PROTECT_TOKENS |
| PPT 扫描 | `scan_pptx` 表格块 `translation_policy` + `BlockRole.TABLE_CELL` |

## 037 P1-A/P1-B（表格可观测 + PPT 执行 policy）

| 项 | 交付 |
| --- | --- |
| P1-A | `table_execution_observability`；预扫摘要 + manifest API + tbltr 后进度展示 |
| P1-B | `pptx_table_exec` + `PPTXTranslator` 按 policy 分流 |

验收：`bash scripts/verify-plan-037-table-observability.sh`

## 遗留

- （035/036 表格 policy 主线已收口；纯图片表 / PPT OCR 仍 out of scope）
