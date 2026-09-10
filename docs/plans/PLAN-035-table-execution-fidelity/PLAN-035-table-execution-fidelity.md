# PLAN-035：表格执行侧数字保护与跨页续表

> 状态：**已完成**
> 验收：[WT-035](../../walkthroughs/WT-035-table-execution-fidelity.md) / `bash scripts/verify-plan-035.sh`
> 前置：PLAN-030-table（几何）、PLAN-033g（块级 policy）、PLAN-033j（翻译/写回）
> 验收门：`bash scripts/verify-plan-035.sh`

## 目标

1. 扫描期标注单元格 `translation_policy`；执行期纯数值不送 LLM，译后硬断言数字 token multiset 不变；manifest 回写 `digits_preserved`。
2. 识别原稿跨页续表（`Table N Continued`），同 `semantic_id` 多 `semantic_occurrence_index`；cell row 全局连续；按 occurrence 写回。

## 子计划

| 编号 | 文件 |
| --- | --- |
| 035a | [PLAN-035a-digit-token-policy.md](./PLAN-035a-digit-token-policy.md) |
| 035b | [PLAN-035b-digit-execution-audit.md](./PLAN-035b-digit-execution-audit.md) |
| 035c | [PLAN-035c-cross-page-scan.md](./PLAN-035c-cross-page-scan.md) |
| 035d | [PLAN-035d-cross-page-exec-verify.md](./PLAN-035d-cross-page-exec-verify.md) |

## 非目标

030-table 几何选型、033j 译文溢出续页语义、DOCX/PPTX 跨页表、PLAN-034。
