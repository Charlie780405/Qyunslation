# PLAN-063b：领域准确度台账

> 父计划：[PLAN-063](./README.md)

目标：用指标回答「是不是翻译得越多、同领域越准」，并在回落时自动接回金标门禁。

## 1. `qyunslation/quality/ledger.py`（新增）

```python
def record_run(session, *, run, excluded_stats, termbase_qa, candidate_summary) -> dict
def domain_metrics(session, *, tenant_id, project_id=None, since=None) -> dict
```

指标集：

- 候选接受率 `approved / (approved + rejected)`
- 词库命中率 `applied / hard_terms_present`
- `termbase_qa.finding_count` 每千词
- 高风险未决数
- 候选噪声率 `excluded_stats 总数 / 抽取总数`
- 术语未遵循数（PLAN-062d 新增的 `violation` 状态计数），须细分两类：
  - **真违规**：curated 词有权威译法而译文未遵循，计入质量下滑。
  - **缺别名**：违规源于词库缺变体（`anti-X`、`X-50/90`），应由 063a 的别名提案消化，**不得**记成质量下滑，否则术语库不完整会伪装成翻译质量退步。
- 接受率按 `source_norm` 去重后再算：候选按 `job_id` 聚合，同一个词跨文档天然多行（PLAN-062 现场 78 行仅对应 23 个不重复词），不去重会把「同词多篇」当成「多词」放大分母。

### screen 盲区指标（必须有）

[qyunslation/glossary/term_screen.py](../../../qyunslation/glossary/term_screen.py) 在 LLM 异常、超 `max_per_doc`、或 `QYUNSLATION_TERM_SCREEN=0` 三种情况下一律判 `generic`，`bridge` 随即记 `SCREEN_GENERIC` 并丢弃该词，而 `excluded_stats` 只回显在 `_summary`（[qyunslation/workbench/bridge.py](../../../qyunslation/workbench/bridge.py) 的 `excluded` 字段）不落库。provider 宕机时整篇缩写静默消失，与 PLAN-047b 的 `QC_CHANNEL_BLIND` 同一类失明。

- `screen_generic_ratio` = `SCREEN_GENERIC` / 抽取总数
- `screen_error_count` = `origin="error"` 的裁定数
- `screen_cap_count` = `origin="cap"` 的裁定数

任一超阈值记 `SCREEN_BLIND`，报告明写「本次候选可能被静默吞掉」。红线：**`SCREEN_GENERIC` 高而候选少不得判为干净**，须与 PLAN-047b 的 `object_qc` 全空同等对待。前提是 `screen_origin` 与 `extracted_total` 随 063a 的 `excluded_stats` 迁移一并落库。

每条记录带指纹，否则跨版本对比无意义：`rules_version`、`termbase_version`、`prompt_version`、`model_id`。`rules_version` 的可信前提是 063a 第 4 节的版本漂移门禁——PLAN-062 现场出现过规则内容变更而版本未 bump。

落盘 JSONL `~/.local/share/qyunslation/quality/ledger.jsonl`（不进 git，与金标 out-root 同风格），DB 只存聚合。

## 2. `scripts/plan063-quality-report.py`（新增）

- 按 tenant/project 出趋势 markdown 报告。
- `--assert-no-regression`：关键指标回落超阈值时 exit 1。
- 回落时提示跑 `QYUNSLATION_PLAN051_LIVE=1 bash scripts/verify-plan-051.sh`，把生产反馈接回既有金标四键门禁（`critical_max=0`、`hard_term_hit_min=0.98`、`forbidden_translation_max=0`、`digit_unit_doi_ref_pass=1.0`）。

红线：**不另造一套阈值**。质量标准的 SSOT 是 PLAN-051 金标四键，台账只负责观测趋势与触发回归，不重新定义「合格」。

## 3. 基线前提

PLAN-062 已交付：curated 概念 393 条，历史噪声候选已回扫（累计 `reject=65`），剩余 pending 78 行 / 23 个不重复词。基线仍需至少 3 篇真实文档才可信，且这 3 篇与 [PLAN-063e](./PLAN-063e-062-closeout.md) 第 4 节的 PLAN-062 LIVE 三项补证合并一次跑完。

首个基线采集前须确认：`term_decision` 已补齐机器裁决（063e 第 1 节），否则接受率的分母缺 65 条拒绝。
