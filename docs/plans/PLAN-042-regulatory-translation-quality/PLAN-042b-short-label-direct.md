# PLAN-042b：短标签与固定字段直译

> 状态：**已完成**
> 父计划：[PLAN-042](./PLAN-042-regulatory-translation-quality.md)

## 交付

1. `glossaries/regulatory-form-fields.csv`：登记表固定字段与短值格确定性译名（layer=`form`）。
2. `qyunslation/glossary/governance.py`：`form` 层优先级 90（org 与 clinical 之间）。
3. `scripts/apply-pdf2zh-042b-short-label.py`：BabelDOC 译前精确直替钩子；命中词表则跳过 LLM。
4. 补丁序登记；`glossary_merge_runtime` 纳入 form 层。

## 验收

- 1–4 字值格与固定字段零漏译（合成夹具）。
- PLAN-003/004 吞吐门保持通过（直替不增加 LLM 调用）。
