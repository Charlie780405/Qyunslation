# PLAN-073d：/next 术语闭环

## 译前

`_launch_translation_run` → `resolve_runtime_terms` → 每任务 `terms-*.csv` → `--glossaries`。

## 译后

规则抽取药名/靶点/量表/缩写 → 去重 → 写入 `document_term_candidate`（带 `translation_run_id`）。

## 复核

RunDetail「本次新术语」面板；批准入库后版本递增。

## 验收

- CLI glossaries 含任务 CSV；候选带 run_id。
