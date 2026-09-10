# PLAN-036：表格数字 policy 跨格式统一与续表金样

承接 [PLAN-035](../PLAN-035-table-execution-fidelity/PLAN-035-table-execution-fidelity.md) WT 下一步 P0/P1。

| 文件 | 内容 |
| --- | --- |
| [PLAN-036-table-policy-unification.md](./PLAN-036-table-policy-unification.md) | 主纲领 |
| [PLAN-036a-policy-ssot-refactor.md](./PLAN-036a-policy-ssot-refactor.md) | 三处规则收敛至 `table_cell_policy` |
| [PLAN-036b-docx-manifest-policy.md](./PLAN-036b-docx-manifest-policy.md) | DOCX 表格块写入 `translation_policy` |
| [PLAN-036c-continued-table-gold.md](./PLAN-036c-continued-table-gold.md) | 真实续表 reference 金样 |
| [PLAN-036d-verify-docs-closure.md](./PLAN-036d-verify-docs-closure.md) | verify + WT/文档收口 |

验收：`bash scripts/verify-plan-036.sh`（编码阶段新增）
