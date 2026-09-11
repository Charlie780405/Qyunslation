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
| test_plan043_quality | PASS |
| verify-plan-043（98516be 后） | **SUMMARY: PASS** |
| 611-2期 P1 汉字 | **177 → 9**（实样 CLI 重译 2026-09-11） |
| 042b hotfix | enumerate 误注入 + lookup suffix + direct_pending 回退 LLM |

实样路径（staging）：`/tmp/plan043-final-98516be/611-2期.no_watermark.en.mono.pdf`

## 遗留

- [ ] P1 孤立短值 `无`（健康受试者）待表格链/写回进一步消除（verify 暂容忍 ≤15 CJK）
- [ ] 表格链剩余表 `SOURCE_RESIDUE`（CLI 缺 DOCUTRANSLATE_BASE_URL 时 mock 译文）

## 部署

| 项 | 值 |
| --- | --- |
| 服务 | `systemctl --user restart pdf2zh.service`（043a 补丁在 ExecStartPre） |
| 补丁 | `apply-pdf2zh-042b-short-label.py` 须重打 live `gui.py` |
