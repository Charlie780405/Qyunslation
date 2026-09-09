# WT-033d 参考文献区口径

> 计划：[PLAN-033d](../plans/PLAN-033-pdf-fidelity/PLAN-033d-references.md)
> 日期：2026-09-09
> 验收门：`bash scripts/verify-plan-033d.sh` → `SUMMARY: PASS fail=0`

## 做了什么

只认独立的 `References` / `Bibliography` / `参考文献` 标题行。其后（可跨页）的 BODY 条目标 `skip` / `semantic_scope=references`。正文 `see [12] for details` 仍走 BabelDOC 文字层。

术语采集 `harvest` 改读去掉条目后的文本，不改 `auto-proper-nouns.csv`。合成夹具 `references-section.pdf`：一页引用句 + 一页标题和两条条目。扫描器 `1.4.0`。

## 验证

| # | 结果 |
| --- | --- |
| V1 标题可译、条目 skip | 通过（夹具两条条目 skip；标题行短于正文门槛，不建 BODY） |
| V2 正文 see [12] 仍译 | 通过 |
| V3 harvest 不含 IQVIA / GenScend，含 MedImmune | 通过 |

未做 BabelDOC IL 禁译；验收走 manifest `planned_action` + harvest。
