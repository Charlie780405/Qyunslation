# PLAN-074：文献/Poster 作者保护、术语审核闭环与乱码门禁

> 状态：**工程闭环；真件回归与生产 WT 待 075c 收束**
> 依赖：PLAN-071（QA/审核门禁）、PLAN-073（术语闭环基础）

## 目标

- 作者元数据整行原样保留；研究单位可翻译但须 QA 确认或修订。
- 每篇文献提取专业术语，在 QA 中逐项批准/拒绝/不翻译；全部处理后才可批准正式稿。
- 写回前清洗乱码，单语/双语成稿执行阻断式检查。

## 子计划

| 子计划 | 目标 |
| --- | --- |
| [074a](./PLAN-074a-author-frontmatter.md) | PDF 前置信息识别与作者块保护 |
| [074b](./PLAN-074b-affiliation-review.md) | 单位审校段、精确 TM、`apply-corrections` 新一代重跑 |
| [074c](./PLAN-074c-term-review-gate.md) | 结构化术语抽取、RunDetail 审校面板、正式门禁 |
| [074d](./PLAN-074d-encoding-gate.md) | 乱码/IL 标签清洗与成稿阻断 |

## 不做

- 不放宽 PLAN-071 批准后才产出正式产物。
- 历史任务不直接改写；需重新 QA 或新版流水线重跑。
- 本轮不覆盖 DOCX/PPTX/图片 OCR。

## 数据库

迁移 `074a0001`（revises `073a0001`）：`review_segment` 增加 run 定位字段；`document_term_candidate.extraction_metadata`。

## 验收

`bash scripts/verify-plan-074.sh` — PASS/FAIL/BLOCKED 三态；真件段见 `scripts/plan074-live-regression.py`。
