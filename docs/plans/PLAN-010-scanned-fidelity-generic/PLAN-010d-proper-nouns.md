# PLAN-010d：专名保护表

## 目标

企业/品牌/人名不被 LLM 幻觉；FDA 机构职务钉死。

## 改动

- `glossaries/proper-nouns.csv`（SSOT）
- `scripts/proper_nouns.py` harvest → `auto-proper-nouns.csv`
- bench/GUI `--glossaries`：manual → auto → qx027n

## 验收

`bash scripts/verify-plan-010.sh after-d`
