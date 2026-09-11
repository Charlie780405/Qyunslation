---
name: pdf-regulatory-form-fidelity
description: >-
  临床监管表单 PDF 完整翻译与表格版式保真：无题注矢量表格、中英混排短标签、单元格回写、
  微字/溢出硬失败、原文清除、固定字段直替、断词约束、受控实体、告警交付。
  触发：监管表单、临床试验登记、无题注表格、单元格漏译、微字、中文残留、
  FONT_BELOW_TARGET、SOURCE_RESIDUE、SHORT_LABEL、WORD_SPLIT、CELL_MERGE、
  PLAN-041、PLAN-042、REGULATORY。
---

# 临床监管表单 PDF 保真（SK-Q003）

## 铁律

1. **无题注也要进表格链**——Word 导出表单常无 `Table N`；走 captionless 网格，禁止运行时 `page.find_tables()`。
2. **有汉字就译**——中英混排/短标签不得因目标语种占比被跳过。
3. **短标签直替（042b）**——登记表固定字段与 1–4 字值格走 `glossaries/regulatory-form-fields.csv`（layer=`form`）译前精确直替，**不要**裸降 `min_text_length`（会冲垮 003/004 吞吐）。
4. **单元格政策**——空格与纯数值 `PRESERVE`；注册号/方案号/电话/邮箱/日期占位保护，丢失即 `TABLE_TOKEN_DRIFT`。
5. **真清除原文**——redaction 后再绘译文；单元格 bbox 可小幅膨胀覆盖多行源 span（042d）。
6. **字号下限只打表格链**——正文 `max(7pt, 源×70%)`，脚注 5.5pt。`FONT_BELOW_TARGET` 进 `table_hard_fail_codes`，**不**进图片 `HARD_FAIL`。
7. **硬错误不落半成品**——`OVERFLOW`（无 continuation）、`MISSING_TARGET`、`SOURCE_RESIDUE`、`CELL_MERGE`、`LABEL_VALUE_SHIFT` 任一出现：不写 `.tbltr.pdf`，`terminal_success=false`。
8. **告警交付（042f）**——表格链失败时 GUI 进度须含「N 个表格未保真」+ 逐表 reason；禁止静默伪成功。
9. **受控实体（042e）**——申办方/医院/院校/人名命中 org/form 词表或保留原文；禁止模型自由猜译。章节序号与 II 期罗马数字走确定性映射。
10. **断词（042c）**——regulatory 画像启用英文整词换行，禁止词内断裂与 CJK/Latin 边界半空格。
11. **实样不入库**——041 经 `QYUNSLATION_PLAN041_SAMPLE`；042 经 `QYUNSLATION_PLAN042_SAMPLE`；缺样本时 verify 输出 `BLOCKED`。
12. **判据**——`bash scripts/verify-plan-041.sh`；质量收口 `bash scripts/verify-plan-042.sh`。

## 错误台账

见 `docs/plans/PLAN-042-regulatory-translation-quality/error-taxonomy.md`（24 类 / 7 族）。
