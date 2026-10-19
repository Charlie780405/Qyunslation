# PLAN-074：文献/Poster 前置元数据保护、术语审核闭环与乱码门禁

> 状态：**作者/英文单位原文保护、术语与乱码门禁持续使用；074b 单位审校已停用。真件回归见 WT-074。**
> 依赖：PLAN-071（QA/审核门禁）、PLAN-073（术语闭环基础）

## 目标

- 作者姓名整行原样保留；英文研究单位默认保留英文原文，不进入单位译名审核。
- 每篇文献提取专业术语，在 QA 中逐项批准/拒绝/不翻译；全部处理后才可批准正式稿。
- 写回前清洗乱码，单语/双语成稿执行阻断式检查。

## 子计划

| 子计划 | 目标 |
| --- | --- |
| [074a](./PLAN-074a-author-frontmatter.md) | PDF 前置信息识别与作者块保护 |
| [074b](./PLAN-074b-affiliation-review.md) | 历史实现：单位审校段、精确 TM、`apply-corrections` 新一代重跑（已停用） |
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

## 当前单位与姓名行为

自 2026-10-19 起，英文单位行和已识别的英文作者姓名由 BabelDOC 原样保留，不生成新的单位审核段，也不参与正式稿门禁。旧版 API 和历史审核记录保留兼容，但 `/next` 不再展示或请求单位审核。
