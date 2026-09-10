# PLAN-039c：L1 生命周期词库

> 状态：**已完成**
> 父计划：[PLAN-039](./PLAN-039-glossary-governance.md)

## 交付

- `glossaries/clinical-lifecycle.csv`（80–150 条，按 domain）
- 迁出 `glossary_db.PRESET_GLOSSARY`，预置改读 L1
- domain：discovery/cmc/nonclinical/clinpharm/clinical/safety/regulatory/stats/ip/heor

## 验收

- primary endpoint → 主要终点；CRSwNP 稳定译法
- `glossary_db.load_glossary` 含 L1 条目
