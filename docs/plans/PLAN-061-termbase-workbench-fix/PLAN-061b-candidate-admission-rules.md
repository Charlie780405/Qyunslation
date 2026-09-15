# PLAN-061b：候选准入规则 SSOT

> 父计划：[PLAN-061](./README.md)

- SSOT：`glossaries/term-candidate-rules.toml`（`version = 061-v1`）。
- 加载器：`qyunslation/glossary/candidate_rules.py`。
- 排除顺序：空 → denylist → 长度（include 豁免）→ exclude.patterns → `classify_cell_policy == PRESERVE` → junk。
- `evidence._synthetic_terms` / `extract_term_pairs` 与 `bridge.append_candidate` 共用排除；政策硬约束循环允许已入库词通过。
- 若存在 `glossaries/term-exclusions.csv`（PLAN-063），加载时并入 denylist。
