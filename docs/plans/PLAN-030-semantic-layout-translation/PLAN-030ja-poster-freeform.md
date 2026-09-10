# PLAN-030ja：D4 海报 FREEFORM 判定

> 状态：**已完成**
> 父计划：[PLAN-030j](./PLAN-030j-layout-debt.md)
> 分支：`feat/PLAN-030j-d4-poster`
> 验收门：`bash scripts/verify-plan-030j.sh`

## 目标

A0 横版海报（宽高比 ~1.41）在 `detect_layout_mode` 返回 `FREEFORM`，九分区不再被误判为 `DOUBLE` 两栏串接。

## 实现

- `qyunslation/structure/layout.py`：`POSTER_FREEFORM_ASPECT=1.38`、`POSTER_MIN_BODY_BLOCKS=6`
- 幻灯阈值 `SLIDE_ASPECT=1.55` 不变
- 测试：`test_poster_is_recognised_as_freeform`、`test_poster_panels_keep_spatial_reading_order`

## 验收

| # | 结果 |
| --- | --- |
| V1 | `verify-plan-030j.sh` PASS |
| V2 | `verify-plan-030h.sh` PASS |
