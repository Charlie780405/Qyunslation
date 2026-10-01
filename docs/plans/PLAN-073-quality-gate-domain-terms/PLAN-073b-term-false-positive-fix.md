# PLAN-073b：术语匹配误报修复

## 根因

`PP`/`No` 经 casefold 误匹配正文；表单层术语套用到文献；短词一律 high risk。

## 交付

- 全大写缩写与 ≤3 字符源词：区分大小写匹配。
- `form`/`regulatory-form-fields` 层仅在「监管申报材料」生效。
- `classify_risk_by_rules`：通用短词不因长度标 high。
- QA 仅检查源文真实命中项；evidence 含命中片段。
- `POST /translation-runs/{id}/requalify` 重跑 QA 不重新翻译。

## 验收

- Dupilumab 病例报告 blocker=0；`PP` 仅大写独立出现才命中。
