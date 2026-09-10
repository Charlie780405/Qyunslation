# PLAN-041e：金标、性能与交付

> 状态：**已完成**
> 父计划：[PLAN-041](./PLAN-041-pdf-regulatory-form-fidelity.md)

## 实施

1. 仓库仅保留匿名合成夹具（`test_plan041_*`）；实样经 `QYUNSLATION_PLAN041_SAMPLE`。
2. `scripts/verify-plan-041.sh` 可用 `QYUNSLATION_VERIFY_PY` 覆盖，缺实样 `BLOCKED`。
3. SK-Q003：`.cursor/skills/pdf-regulatory-form-fidelity/`。
4. `verify-release.sh` 增加 041 sample 门。

## 回归证据

| 门禁 | 结果 |
| --- | --- |
| structure 全量 | `480 passed` |
| verify-plan-028 | PASS；19 页冷扫 median `1.512s` max `1.594s` |
| verify-plan-033k | PASS |
| verify-plan-035 | PASS |
| verify-plan-036 | PASS |
| verify-plan-041 + 实样 | PASS |
| 7 页扫描 | `0.455 / 0.275 / 0.272s`（`<5s`） |
