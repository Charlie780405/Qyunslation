# PLAN-058f：术语策略注入、译后 QA 与正式稿门禁

> 父计划：[PLAN-058](./README.md)

## 交付

- 将硬约束策略注入现有工作流的 glossary 边界，不把全量词库写入 custom prompt。
- 文本和 PDF/Office 转 Markdown 路径保存译前可比较文本，译后校验首选译法和禁用译法。
- 发现硬术语缺失或禁用译法时阻止正式稿导出，并在任务 statistics 中返回定位信息。
- DOCX/PPTX/XLSX/图片等二进制原生写回路径明确返回 QA unavailable，由其结构/版式 QA 负责，不伪造通过。

## 完成定义

- exact/alias 硬词遵从率可计算，低置信 semantic suggestion 不会覆盖译文。
- QA 结果包含 available、passed、finding_count、findings 和 termbase_version。
- 术语策略应用失败会进入任务日志，不静默宣称已注入。
