# WT-038f：版式弱项收口

日期：2026-09-10  
纲领：[PLAN-038f](../plans/PLAN-038-gap-closure/PLAN-038f-layout-weak-items.md)

## 交付

| G-ID | 结果 |
| --- | --- |
| G-CAP-003 | **wontfix**：`cap_body_gap` 不进 BabelDOC fork；仓内 `font_style.cap_body_gap` 仅本地排版用 |
| G-CAP-004 | **closed**：`scripts/probe-figure-ink-residue.py` + 单测；WARN exit=2，不进 release hard-fail |

## 验收

```bash
bash scripts/verify-plan-038f.sh
```
