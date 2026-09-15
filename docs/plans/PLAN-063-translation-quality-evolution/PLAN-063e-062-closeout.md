# PLAN-063e：PLAN-062 收尾与证据回填

> 父计划：[PLAN-063](./README.md)
> 本子计划是 PLAN-063 的**第 0 步**：063a 的规则归纳读裁决历史，而 PLAN-062 的机器裁决没有留下裁决行，先补齐再开工。

## 1. 机器裁决必须入 `TermDecision`

[scripts/plan062-purge-stale-candidates.py](../../../scripts/plan062-purge-stale-candidates.py) 直接改 `candidate.status` 并只记一条聚合 audit，绕过唯一写 `TermDecision` 的 `decide_candidate`（[qyunslation/persist/candidate_repo.py](../../../qyunslation/persist/candidate_repo.py) 第 415 行）。PLAN-062 现场两次回扫 `reject=19` + `reject=46` 共 65 条拒绝，在库中没有裁决行。

交付：

- purge 改走 `decide_candidate`（`action="reject"`、`actor_sub="plan062-purge"`），或新增 `machine_reject` 通道写同一张 `term_decision` 表。
- 脚本里 `extras` 列表构造后从未使用，逐条原因码直接丢弃；改为汇总打印并落 run 级统计，口径与 `excluded_stats` 一致。
- 一次性回填脚本 `scripts/plan063e-backfill-machine-decisions.py`：对已是 `rejected` 且 `decision_note` 以 `plan062 purge:` 开头的候选补记裁决行，原因码从 `decision_note` 反解。

红线：回填只补 `TermDecision`，**不改**候选状态、不动 Concept 库。

## 2. 手改 denylist 回填 `term-exclusions.csv`

PLAN-062 现场把 `TARGET`、`DERM`、`ADA`、`ACAD`、`DERMATOL`、`Inc`、`USA`、`MBA`、`PHARMACEUTICAL` 手工写进 [glossaries/term-candidate-rules.toml](../../../glossaries/term-candidate-rules.toml) 的 `denylist`，`version` 仍是 `062-v1`。规则内容变了指纹没变，063b 的台账无法按版本对比。

交付：

- 上述条目回填为 `term-exclusions.csv` 首批行（`reason=plan062-manual`、`scope=global`、`decided_by=plan062-purge`）。
- TOML `denylist` 只保留统计/语法类停用词，领域歧义词交给 CSV。
- 回填后 bump `version` 至 `063-v1`，并同步 `tests/workbench/test_plan061_candidate_rules.py` 的版本断言。

## 3. `--screen-pending` 排空历史候选

剩余 78 行 / 23 个不重复词：`EASI-50`、`EASI-90`、`PP-NRS`、`IL-4`、`IL-13`、`dupilumab`、`ECZTEND`、`NCT03131648` 等，只有再次出现在新译文里才会被 `screen_terms` 裁定。

交付：`scripts/plan063-evolve-term-rules.py --screen-pending`，对历史 pending 批量走三级裁定，产出提案（收录 / 排除 / 别名），**只出提案不自动落库**。

其中两类变体暴露 062d 的查库口径缺口，提案须覆盖：

- 前缀变体 `anti-tralokinumab` 未匹配到 curated 的 `tralokinumab`（`anti-`、`non-`、`pre-`）。
- 数字后缀 `EASI-50` / `EASI-90` 未匹配到 curated 的 `EASI-75`。
- 大小写 `dermatitis` 与 `Dermatitis` 跨 job 各占一行（`source_norm` 已 casefold，跨 job 重复属设计内，台账须按 `source_norm` 去重后再算接受率）。

## 4. PLAN-062 LIVE 三项补证

[WT-062](../../walkthroughs/WT-062-termbase-evolution.md) 的五项实点只证了两项（工作台文案与筛选项在现场 `gui.py`），以下三项需真实文档：

1. 进度条在插图/表格后处理阶段持续更新，不再长期停在 95%。
2. 保存后自动进入下一条。
3. 「关联已有词条」下拉能选出 Concept，不必手输 UUID。

与 063b 首个基线所需的 3 篇真实文档合并一次跑完，证据写回 WT-062 的 LIVE 段并在 WT-063 引用。

## 验收

- `term_decision` 中 `actor_sub='plan062-purge'` 的行数等于历史机器拒绝数。
- `term-exclusions.csv` 存在且 `load_rules()` 的 denylist 含回填条目；`rules_version() == "063-v1"`。
- `--screen-pending` 只读不写（断言 DB 无变更）。
- WT-062 LIVE 三项有截图或 DOM 证据。
