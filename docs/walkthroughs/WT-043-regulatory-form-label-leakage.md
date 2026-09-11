# WT-043：监管表单字段标签漏译闭环

日期：2026-09-11  
纲领：[PLAN-043](../plans/PLAN-043-regulatory-form-label-leakage/PLAN-043-regulatory-form-label-leakage.md)

## 诊断结论（实施前）

| 观察 | 结论 |
| --- | --- |
| 文字层长段落 | BabelDOC 路径基本正常 |
| 字段标签漏译 | 34/46 短标签来自表格单元格；12 表检出但无 `.tbltr.pdf` |
| 042b 回归 | P1 汉字 89→177（写回 composition 失败） |

## 实施记录

| 子计划 | 状态 | 交付 |
| --- | --- | --- |
| 043a | 已完成 | `apply-pdf2zh-042b-short-label.py` → `post_translate_paragraph`；失败不 skip LLM |
| 043b | 已完成 | form 词表 +11；suffix 拼回；`周清红`→`Zhou Qinghong` |
| 043c | 已完成 | `TABLE_QC_SOFT`；PROTECT_TOKENS 回退原文；部分表成功仍写 `.tbltr.pdf` |
| 043d | 已完成 | `verify-plan-043.sh`；SK-Q003 扩写；本 WT |

## 验证

```bash
bash scripts/verify-plan-043.sh
# EN 实样门：QYUNSLATION_PLAN043_EN_OUTPUT=/path/to.en.mono.pdf
```

| 门禁 | 结果 |
| --- | --- |
| test_plan043_quality | 本地 PASS |
| verify-plan-042 回归 | 见部署记录 |

## 遗留

- [ ] 生产 GUI 重译 611-2期 后手测 P1 L1 标签清单
- [ ] 表格链剩余 7/12 表 `TABLE_DIGIT_DRIFT`（长 narrative 格，依赖 LLM token 保真）

## 部署

| 项 | 值 |
| --- | --- |
| 服务 | `systemctl --user restart pdf2zh.service`（043a 补丁在 ExecStartPre） |
| 补丁 | `apply-pdf2zh-042b-short-label.py` 须重打 live `gui.py` |
