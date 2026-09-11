# PLAN-042f：告警交付、全文质量门与金标

> 状态：**已完成**
> 父计划：[PLAN-042](./PLAN-042-regulatory-translation-quality.md)

## 交付

1. `execution_table_fidelity_hint` 汇总「N 个表格未保真」+ 逐表 reason。
2. `apply-pdf2zh-docimg` 确保生产 GUI 注入 hint（现场补齐）。
3. 全文级字号/CJK 残留门：`qyunslation/structure/page_qc.py`。
4. `scripts/verify-plan-042.sh` 接入 `verify-release.sh`（sample 模式）。
5. WT-042；扩写 SK-Q003。

## 验收

- 表格链硬失败时 GUI 进度文案含告警。
- 成功路径无告警。
- verify-042 PASS（缺实样 BLOCKED）。
