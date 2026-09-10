# PLAN-038f：版式弱项收口

> 状态：**已完成**
> 父计划：[PLAN-038](./PLAN-038-gap-closure.md)
> 归属缺口：G-CAP-003、G-CAP-004
> 验收：[WT-038f](../../walkthroughs/WT-038f-layout-weak-items.md) / `bash scripts/verify-plan-038f.sh`

## 决策

| G-ID | 决策 | 理由 |
| --- | --- | --- |
| G-CAP-003 | **wontfix** | `cap_body_gap` 须改 BabelDOC 上游；033 已诚实降级，本仓不 fork BabelDOC 排版 |
| G-CAP-004 | **closed（探针）** | 增加轻量 Figure 残影探针（原/译 pixmap 差分阈值告警），不 block 发布 |

## 交付

1. registry + WT-033n 回写
2. `scripts/probe-figure-ink-residue.py` + `tests/structure/test_plan038f_figure_residue.py`
3. `scripts/verify-plan-038f.sh`

## 验收

- G-CAP-003 = wontfix；G-CAP-004 = closed
- 探针单测 PASS；默认 WARN 不 fail release
