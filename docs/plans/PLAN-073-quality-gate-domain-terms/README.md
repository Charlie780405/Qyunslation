# PLAN-073：质量门禁真实化、模型分级接入与自免领域术语闭环

> 状态：**已上线；DeepSeek/浏览器/全量机器金标待 075d/075e 收束**
> 依赖：PLAN-071（QA/审核门禁）、PLAN-072（工作台持久化）、PLAN-058/060（术语库）

## 目标

修复「卡在保存 PDF」的误报与 UI 失真；合并重复进度区；资料等级真正驱动翻译模型并接入 DeepSeek；`/next` 接入术语译前约束与译后抽取；建立自免领域术语包与金标评测。

## 子计划

| 子计划 | 目标 |
| --- | --- |
| [073a](./PLAN-073a-progress-status-truth.md) | 进度去重 + qa_blocked 状态真实化 |
| [073b](./PLAN-073b-term-false-positive-fix.md) | 术语匹配误报修复 + requalify |
| [073c](./PLAN-073c-model-classification-deepseek.md) | 模型档驱动 pdf2zh + DeepSeek |
| [073d](./PLAN-073d-next-term-loop.md) | /next 术语译前注入 + 译后抽取 |
| [073e](./PLAN-073e-autoimmune-domain-gold.md) | 自免词包 + 金标评测 |

## 不做

- 不放宽 PLAN-071 批准后才产出正式产物。
- 机密资料不调用任何外部模型。
- 不迁移旧 Gradio 任务。

## 数据库

迁移 `073a0001`（revises `072a0001`）：`concept.applies_to_profiles`、`document_term_candidate.translation_run_id`。

## 验收

`bash scripts/verify-plan-073.sh` — PASS/FAIL/BLOCKED 三态。
