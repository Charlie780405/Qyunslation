# PLAN-074c：术语审核闭环

## 交付

- [qyunslation/workbench/term_extract.py](../../../qyunslation/workbench/term_extract.py)：规则 + 结构化模型补充；`TERM_EXTRACTION_DEGRADED`。
- RunDetail：[TermReviewPanel.vue](../../../frontend/src/next/components/TermReviewPanel.vue)、单条/批量裁决 API。
- `_formal_gate`：未处理术语、未确认单位、QA blocker、已取代产物均拦截批准。

## 验收

`tests/workbench/test_plan074_term_extract.py`；`tests/api/test_plan071e_review_gate.py`；真件术语金标（plan074-live-regression）。
