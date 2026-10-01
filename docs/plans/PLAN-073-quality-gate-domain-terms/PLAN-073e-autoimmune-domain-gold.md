# PLAN-073e：自免领域术语包与金标评测

## 交付

- `glossaries/domain-autoimmune.csv` 种子词包。
- 药名漂移表补充 dupilumab 等。
- `tests/gold/autoimmune/` 金标集（10 份结构）。
- `scripts/plan073-domain-eval.py` 评测台账。

## 领先判据（WT）

术语准确率 ≥98%、药名漂移 0、QA 误报 ≤1/文档。
