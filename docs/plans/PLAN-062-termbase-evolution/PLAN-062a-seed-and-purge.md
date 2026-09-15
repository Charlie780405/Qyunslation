# PLAN-062a：补 seed 与清库

> 父计划：[PLAN-062](./README.md)

## 交付

1. 跑 `scripts/plan034d-import-csv.py`，验收 `curated_concepts ≥ 350`。
2. 把 `auto-proper-nouns.csv` 中人工确认的领域缩写提升进 curated 表后再导入。
3. `scripts/plan062-purge-stale-candidates.py`：噪声 `rejected`，已入库 `applied`。

## 不提升

`III`、`TARGET`、`DERM`、`ADA`、`JAMA`、`JID` 及试验/注册库歧义词。上述歧义词与期刊/机构碎片（`ACAD`、`DERMATOL`、`Inc`、`USA`）进 denylist，purge 直接 `rejected`，不进待确认。
