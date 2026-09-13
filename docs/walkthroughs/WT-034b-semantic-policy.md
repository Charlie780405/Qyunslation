# WT-034b：Manifest 1.3.0 语义策略

对应 [PLAN-034b](../plans/PLAN-034-pharma-rd-mvp/PLAN-034b-semantic-policy.md)。

## 执行摘要

将 `CURRENT_SCHEMA_VERSION` 升至 **1.3.0**，新增 `TERM_ONLY` / `HUMAN_REVIEW`，扩展 `SourceStyle.color` / `line_height`、`DocumentInfo.document_domain` / `risk_level`、`ProducerInfo` 术语/TM 版本占位；合同与 JSON Schema 与模型对齐；执行侧对新策略 fail-closed（不送 LLM）。

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `CURRENT_SCHEMA_VERSION == "1.3.0"` | PASS |
| V2 | `pytest tests/structure/test_plan034b_manifest_13.py tests/structure/test_manifest_contract.py` | PASS |
| V3 | `bash scripts/verify-plan-034b.sh` | `SUMMARY: PASS` |
| V4 | 1.2.0 fixture 仍可 `model_validate` | PASS |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/structure/models.py` | 1.3.0 + 新枚举/字段 |
| `docs/contracts/document-structure-manifest-v1.md` | 版本与增量表 |
| `docs/contracts/document-structure-manifest-v1.schema.json` | 由模型再生 |
| `table_translate.py` / `docx_table_exec.py` / `pptx_table_exec.py` | 延期策略不送 LLM |
| `scripts/verify-plan-034b.sh` | 034b 门 |
| `scripts/verify-plan-033g.sh` | schema 断言跟版 1.3.0 |
