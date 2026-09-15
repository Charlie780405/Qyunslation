# ADR-032：术语规则进化必须人工 promote

- 状态：accepted
- 日期：2026-09-15
- 计划：PLAN-063

## 决定

规则进化 `--report` / `--screen-pending` 只读不写；`--promote PROP` 才改 `term-exclusions.csv` / `term-candidate-rules.toml`，并必须 bump `version`、登记 fingerprint。

## 理由

误杀一个真术语的成本（静默丢词、污染已交付译文、难以追溯）远高于人工一次 promote。PLAN-062 现场手改 denylist 未 bump 版本，已证明自动落地会让台账指纹失真。

## 后果

- 机器裁决可入 `TermDecision`，但单独的机器拒绝不构成 denylist 提案。
- 误杀保留清单（`tralokinumab` / `IL-13` / `NHS` / `EASI` / `BSA` / `ABC-101`）的提案直接丢弃。
