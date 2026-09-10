# WT-030ja D4 海报 FREEFORM 判定

> 计划：[PLAN-030ja](../plans/PLAN-030-semantic-layout-translation/PLAN-030ja-poster-freeform.md)
> 分支：`feat/PLAN-030j-d4-poster`
> 日期：2026-09-10

## 变更

- `layout.py`：宽横版（aspect ≥ 1.38）且正文块 ≥ 6 时返回 `FREEFORM`
- 金样 `poster-sections.pdf`：`detect_layout_mode` 由 `DOUBLE` → `FREEFORM`
- 阅读顺序：九分区按 `(y0, x0)` 空间排序，不再两栏串接

## 门禁

| 门禁 | 结果 |
| --- | --- |
| verify-plan-030j.sh | PASS |
| verify-plan-030h.sh | PASS |

## 下阶段输入

- D1/D2：三/四栏 → `MULTI`，中栏不吞左栏
- D3：少块双栏不短路 `SINGLE`
- D5：`content_profile` 与容器解耦
