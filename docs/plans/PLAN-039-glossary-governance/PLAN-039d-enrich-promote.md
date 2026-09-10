# PLAN-039d：候选挖词与晋升

> 状态：**已完成**
> 父计划：[PLAN-039](./PLAN-039-glossary-governance.md)

## 交付

- `scripts/glossary_enrich.py`：从任务 glossary CSV / 对照文本抽候选 → staging
- `scripts/glossary_promote.py`：staging → org/clinical/project
- staging 路径：`glossaries/staging/`（gitignore）

## 验收

- dry-run 产出 staging；promote 写入 curated 并去重
