# PLAN-036d：verify 与文档收口

> 状态：**待批准**

## 交付

1. **`scripts/verify-plan-036.sh`**
   - compile 036 触及模块
   - `pytest tests/structure/test_plan036_*.py`
   - `verify-plan-035.sh` 回归
2. **（可选）** `verify-release.sh` 增加 036 门（在 035 之后）
3. **`docs/walkthroughs/WT-036-table-policy-unification.md`**
4. 补丁 [WT-030-table](../../walkthroughs/WT-030-table-closure.md)：
   - 「跨页续表 out of scope」→ 已完成（035 + 036 金样）
5. 更新 [PLAN-035 WT](../../walkthroughs/WT-035-table-execution-fidelity.md) 遗留项勾选状态

## 验收

```bash
QYUNSLATION_VERIFY_PY=/home/dev/qyunslation/.venv/bin/python bash scripts/verify-plan-036.sh
# SUMMARY: PASS fail=0
```

036c 样本 BLOCKED 时：verify 脚本应 **FAIL** 并提示 `CONTINUED_TABLE_GOLD_MISSING`，不得 skip-pass。
