# WT-039：临床与专名术语治理

日期：2026-09-10  
纲领：[PLAN-039](../plans/PLAN-039-glossary-governance/PLAN-039-glossary-governance.md)

## 交付摘要

| 子计划 | 交付 |
| --- | --- |
| 039a | `qyunslation/glossary/governance.py` schema + `merge_by_priority` |
| 039b | `glossaries/org-proper-nouns.csv`；景行↔GenScend 双向；剔除页码/日期垃圾 |
| 039c | `glossaries/clinical-lifecycle.csv`；`glossary_db.PRESET` 改读 L1 |
| 039d | `scripts/glossary_enrich.py` / `glossary_promote.py`；`glossaries/staging/`（gitignore） |
| 039e | `scripts/glossary_merge_runtime.py` → `/home/dev/pdf2zh/glossaries/merged.csv`；sidecar/GUI 同读 |
| 039f | 本文档；`verify-release.sh` 增加 039 门 |

## 日常用法

```bash
# 改 L0/L1 后重新并表
.venv/bin/python scripts/glossary_merge_runtime.py

# 从任务 glossary 挖候选
.venv/bin/python scripts/glossary_enrich.py path/to/task.glossary.csv

# 晋升到 curated
.venv/bin/python scripts/glossary_promote.py glossaries/staging/candidates.csv \
  --layer org --source '景行生物'
```

## 验收

```bash
bash scripts/verify-plan-039.sh
```

## 金句

| source | target |
| --- | --- |
| 景行生物 / 江苏景行生物医药有限公司 | GenScend |
| Jiangsu GenScend Biopharma Co., Ltd. | 江苏景行生物医药有限公司 |
| GenScend | GenScend（非金斯瑞） |
| primary endpoint | 主要终点 |
| CRSwNP | 伴鼻息肉的慢性鼻窦炎 |

## 部署

| 项 | 值 |
| --- | --- |
| merge | `8ac8749`（039a–f → origin/main） |
| 服务 | `pdf2zh.service`、`qyunslation-office.service` |
| verify-plan-039 | PASS |
