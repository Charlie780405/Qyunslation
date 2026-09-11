# PLAN-045d：插图面板字母与底擦

> 状态：已完成
> 父计划：[PLAN-045](./PLAN-045-literature-pdf-fidelity.md)
> Skill：SK-Q002

## 交付

1. `^[A-F][.)]?$` → `tier=panel_letter`，跨背景同组；字号取墨迹中位数，不参与正文 `k`。
2. 全局 `k` 下限 `TIER_K_FLOOR`（默认 0.85）；剔除 panel/outlier。
3. 擦除上限 2 轮；仍残留 → `SOURCE_INK_LEFT` 单图熔断留原图。

## 验收

- `tests/extensions/test_plan045_image_panel.py`
