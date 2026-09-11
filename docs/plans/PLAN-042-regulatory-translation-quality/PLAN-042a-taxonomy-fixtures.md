# PLAN-042a：错误台账与合成夹具基线

> 状态：**已完成**
> 父计划：[PLAN-042](./PLAN-042-regulatory-translation-quality.md)

## 交付

1. [error-taxonomy.md](./error-taxonomy.md) 24 类受控台账。
2. `tests/structure/plan042_fixtures.py`：匿名合成夹具（短标签格、长列表格、多行机构名格、键值对格、断词压力格）。
3. `tests/structure/test_plan042_taxonomy_fixtures.py`：每族至少一个失败夹具可检出。

## 验收

- 台账 24 条齐全。
- 合成夹具不入库二进制；测试内联生成。
- 实样经 `QYUNSLATION_PLAN042_SAMPLE`，缺则 skip/BLOCKED。
