# PLAN-058g：金标评测、性能回归与交付

> 父计划：[PLAN-058](./README.md)

## 交付

- `qyunslation.glossary.evaluation` 输出 Recall@5、出现级召回、Top-1 Precision、精确检出和高置信覆盖率。
- 聚焦单测覆盖 resolver、迁移、项目隔离、embedding 降级、API、别名/缩写和 QA 门禁。
- `scripts/verify-plan-058.sh` 默认使用仓库 `.venv`，支持 `QYUNSLATION_VERIFY_PY`；LIVE 条件缺失报告 BLOCKED。
- WT 记录代码基线、测试、数据库迁移、embedding 状态、金标结果和未完成门项。

## 完成定义

- 默认工程门不调用真实 LLM，不伪造金标结果。
- LIVE 金标达到 PLAN-058 规定阈值才可报告产品质量通过。
- 依赖门 034d、034g、039、050e、051、055 的结果逐项记录，任一 FAIL/BLOCKED 不得标记产品门完成。
