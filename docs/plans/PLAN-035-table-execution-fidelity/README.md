# PLAN-035：表格执行侧数字保护与跨页续表

承接 [PLAN-030-table](../PLAN-030-semantic-layout-translation/PLAN-030-table-pdf-cell-reconstruction.md) Task 4 与跨页续表遗留项。

| 文件 | 内容 |
| --- | --- |
| [PLAN-035-table-execution-fidelity.md](./PLAN-035-table-execution-fidelity.md) | 主纲领 |
| [PLAN-035a-digit-token-policy.md](./PLAN-035a-digit-token-policy.md) | 数字 policy SSOT |
| [PLAN-035b-digit-execution-audit.md](./PLAN-035b-digit-execution-audit.md) | 执行断言与 manifest 回写 |
| [PLAN-035c-cross-page-scan.md](./PLAN-035c-cross-page-scan.md) | 跨页续表扫描 |
| [PLAN-035d-cross-page-exec-verify.md](./PLAN-035d-cross-page-exec-verify.md) | 执行与验收门 |

验收：`bash scripts/verify-plan-035.sh` / 发布总门 `bash scripts/verify-release.sh`
