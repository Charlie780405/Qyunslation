---
name: pdf-regulatory-form-fidelity
description: >-
  临床监管表单 PDF 完整翻译与表格版式保真：无题注矢量表格、中英混排短标签、单元格回写、
  微字/溢出硬失败、原文清除。触发：监管表单、临床试验登记、无题注表格、单元格漏译、
  微字、中文残留、FONT_BELOW_TARGET、SOURCE_RESIDUE、PLAN-041、REGULATORY。
---

# 临床监管表单 PDF 保真（SK-Q003）

## 铁律

1. **无题注也要进表格链**——Word 导出表单常无 `Table N`；走 captionless 网格，禁止运行时 `page.find_tables()`。
2. **有汉字就译**——中英混排/短标签不得因目标语种占比被跳过。
3. **单元格政策**——空格与纯数值 `PRESERVE`；注册号/方案号/电话/邮箱/日期占位保护，丢失即 `TABLE_TOKEN_DRIFT`。
4. **真清除原文**——redaction 后再绘译文；白色遮挡不算完成。
5. **字号下限只打表格链**——正文 `max(7pt, 源×70%)`，脚注 5.5pt。`FONT_BELOW_TARGET` 进 `table_hard_fail_codes`，**不**进图片 `HARD_FAIL`。
6. **硬错误不落半成品**——`OVERFLOW`（无 continuation）、`MISSING_TARGET`、`SOURCE_RESIDUE`、`ROLE_SIZE_DRIFT` 任一出现：不写 `.tbltr.pdf`，`terminal_success=false`。
7. **实样不入库**——只经 `QYUNSLATION_PLAN041_SAMPLE`；缺样本时 verify 输出 `BLOCKED`。
8. **判据**——`bash scripts/verify-plan-041.sh`。
