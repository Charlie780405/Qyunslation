# PLAN-045b：参考文献粘连序号 PRESERVE

> 状态：已完成
> 父计划：[PLAN-045](./PLAN-045-literature-pdf-fidelity.md)

## 交付

1. `references.ENTRY_RE` 支持 `[n]` / `n.` / `n Author` / `1Langanan` 粘连。
2. `babeldoc_policy` 入区后整段 PRESERVE；`reset_preserve_gate` 仅 `translate(docs)` 入口。
3. 现场 `apply-pdf2zh-fidelity-033h.py` 含 `_QY_033H_PRESERVE`。

## 验收

- `tests/structure/test_plan045_references.py`、`test_references.py`
- `verify-plan-033h.sh`
