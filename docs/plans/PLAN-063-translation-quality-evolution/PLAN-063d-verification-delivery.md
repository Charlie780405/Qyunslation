# PLAN-063d：验收与交付

> 父计划：[PLAN-063](./README.md)

## 测试

- `tests/quality/test_plan063_ledger.py` — 指标计算、指纹写入、JSONL 落盘路径；`screen_generic_ratio` 超阈值必须置 `SCREEN_BLIND`；`violation` 细分为真违规与缺别名；接受率按 `source_norm` 去重。
- `tests/scripts/test_plan063_evolve_rules.py` — 含关键用例「误杀保留清单的提案必须被丢弃」；`--report` 与 `--screen-pending` 不得写 DB；单独的机器拒绝不得单独构成 denylist 提案。
- `tests/persist/test_plan063_migration.py` — `excluded_stats` 迁移升降级，含 `SCREEN_GENERIC` / `SCREEN_NOISE` 与裁定 `origin`。
- `tests/workbench/test_plan063e_machine_decision.py` — purge 等机器裁决必须产生 `TermDecision`；回填脚本幂等且不改候选状态与 Concept 库。
- `tests/workbench/test_plan063_batch_guard.py` — batch-approve 不得把 `violation` 当 `pending` 处理。`decide_candidate` 已放行 `violation` 状态（[qyunslation/persist/candidate_repo.py](../../../qyunslation/persist/candidate_repo.py) 的 `{"pending", "pending_admin", "violation"}`），目前只靠 high-risk 与 `match_type` 白名单拦截，低风险 exact 违规仍有被批量通过的口子。
- 规则版本：内容哈希变而 `version` 未 bump 时门禁必须 fail。

## `scripts/verify-plan-063.sh`

沿用 [verify-plan-061.sh](../../../scripts/verify-plan-061.sh) 的 pass/fail/blocked 三态骨架与退出码 0/1/2：

1. 静态文件存在（PLAN 目录 6 文件、WT、`term-exclusions.csv` schema、`quality/ledger.py`、两个脚本）。
2. `docs/plans/README.md` 索引断言。
3. `compileall qyunslation/quality scripts/plan063-*.py`。
4. focused pytest（063 五个新文件 + PLAN-062 相关回归）。
5. `--report --dry-run` 冒烟：确认只读不写。
6. skill / registry / **六条**错误签名存在性断言。
7. 规则版本漂移门：`term-candidate-rules.toml` 内容哈希与 `registry.md` 登记的 `version` 一致。
8. 依赖门（三项，任一不满足报 `BLOCKED`）：
   - `QYUNSLATION_PLAN063_FULL=1` 时先跑 `verify-plan-062.sh` 且通过。
   - PLAN-062 LIVE 三项在 [WT-062](../../walkthroughs/WT-062-termbase-evolution.md) 有证据（进度条、保存下一条、Concept 下拉）。
   - GUI 补丁标记清单现场与仓库 parity：现场 `gui.py` 含仓库补丁声明的全部标记（如 `_qy_tbl_progress`、`0.96 + 0.03`、`需人工填写`、`术语未遵循`、`keep_selection`）。PLAN-062 现场缺过进度回调而脚本仍打印 `already patched`，判据必须是清单而非单一 marker。

## ADR

`docs/decisions/ADR-032-term-rule-evolution-human-promote.md`：记录「规则进化为何不自动落地」——误杀一个真术语的成本（静默丢词、污染已交付译文、难以追溯）远高于人工一次 promote 的成本。

## 文档

- `docs/walkthroughs/WT-063-translation-quality-evolution.md`
- `docs/plans/README.md` 索引行

## 交付前提

PLAN-062 已 PASS（`verify-plan-062.sh` fail=0，翻译栈双进程部署指纹一致）。其遗留的证据回填与 LIVE 补证归 [PLAN-063e](./PLAN-063e-062-closeout.md)，**不回改** PLAN-062 的验收结论。若上述三项依赖门任一不满足，`verify-plan-063.sh` 报 `BLOCKED` 而非 `FAIL`，且不得写成 PASS。
