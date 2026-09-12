# PLAN-046b：摘要段落重建

> 状态：已完成
> 父计划：[PLAN-046](./PLAN-046-literature-structure-fidelity.md)

## 交付

1. `scripts/apply-pdf2zh-046b-para-merge.py`：挂在 `merge_alternating_line_number_paragraphs` 之后合并续行碎片。
2. typesetting `min_scale` 可读 `_QY_MIN_SCALE`；literature profile `min_scale=0.8`。
3. `detect_drug_name_drift`（只告警不替换）。

## 验收

- `tests/structure/test_plan046b_para_merge.py`
- site-packages 含 `_QY_046B_PARA_MERGE` 与 `_QY_MIN_SCALE`
