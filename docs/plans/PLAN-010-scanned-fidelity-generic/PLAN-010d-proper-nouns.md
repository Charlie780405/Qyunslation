# PLAN-010d：专名保护表

## 目标

企业/品牌/人名不被 LLM 幻觉；FDA 机构职务钉死。

## 改动

- `glossaries/proper-nouns.csv`（历史 SSOT）
- `scripts/proper_nouns.py` harvest → `auto-proper-nouns.csv`
- bench/GUI `--glossaries`：manual → auto → qx027n

## 后续

**治理与双向专名（景行↔GenScend 等）已由 [PLAN-039](../PLAN-039-glossary-governance/PLAN-039-glossary-governance.md) 承接。**  
现行 SSOT：`glossaries/org-proper-nouns.csv`；运行时：`merged.csv`。

## 验收

`bash scripts/verify-plan-010.sh after-d`
