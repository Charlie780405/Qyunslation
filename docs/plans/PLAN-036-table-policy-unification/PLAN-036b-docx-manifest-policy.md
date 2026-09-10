# PLAN-036b：DOCX 表格 manifest translation_policy

> 状态：**待批准**
> 前置：036a

## 改

[`scan_docx.py`](../../../qyunslation/structure/scan_docx.py) 表格块构造（约 `_append_table_object` / cell loop）：

- 每 cell：`translation_policy=classify_cell_policy(segment.text)`
- 保留 `role=TABLE_CELL` / header 等既有 role 逻辑
- 删除「numeric 时重建无 policy 的 TranslatableBlock」特殊分支

## 不改

- DOCX 原位翻译执行器大改（若当前不消费 policy，在 WT-036 记 INFO）
- PPTX 表格（可 036 后 follow-up）

## 测试

- `tests/structure/test_plan036_docx_table_policy.py`：parity.docx 或 synthetic review.docx 中 numeric cell 为 `PRESERVE`，文本 cell 为 `TRANSLATE`/`PROTECT_TOKENS`

## 验收

- DOCX scan manifest 表格块均含非空 `translation_policy`（空 cell 除外）
