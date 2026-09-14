# PLAN-051b：MQM 计数器

> 状态：**已实现**
> 父计划：[PLAN-051](./PLAN-051-gold-pharma-mqm.md)
> 依赖：051a 产物（或夹具 manifest）
> 验收：`pytest tests/gold/test_plan051b_score.py`

## 目标

从 051a 产物 + 术语 SSOT 聚成 `evaluate_baseline_report` 四键；映射 Pharma-MQM 1.0.0。

## 交付

| 路径 | 说明 |
| --- | --- |
| `qyunslation/gold/plan051_score.py` | 计分核心 |
| `scripts/plan051-score-gold.py` | 读一批 run-manifest → JSON 报告 |
| `tests/gold/test_plan051b_score.py` | 脏/净/拒 skeleton |

## 四键

- `critical_count`：`TABLE_DIGIT_DRIFT`、`REF_GLUED_LEAK`、034f critical（doses/numbers/references）、`detect_forbidden`
- `forbidden_translation_count`：禁用译法命中数
- `hard_term_hit_rate`：`build_merged_dict` 原文出现 → 译文须含指定译法；分母 0 → 1.0
- `digit_unit_doi_ref_pass_rate`：数字/单位/百分比/日期/引用/参考文献无 critical 的条目占比

PM-C2 / Minor → `notes`，不进四键（除非已标 critical）。

报告必须含：`mode: full-retranslate`、四键、`real_scored`、`synthetic_ran`、`per_class_real`、`git_head`、`model_id`、`pharma_mqm`。

`mode != full-retranslate` → **FAIL**。

## 判据

- 注入 `TABLE_DIGIT_DRIFT` → evaluate fail
- 干净 QC + 术语全中 → evaluate pass
- 喂 skeleton JSON → 拒绝
- 不跑 Ollama

## Out of Scope

- COMET / 新分类器
- 改 `thresholds.toml`；Major 自动升 Critical
