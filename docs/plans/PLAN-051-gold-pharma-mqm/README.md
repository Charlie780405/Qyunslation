# PLAN-051：金标整本 Pharma-MQM 门

> 状态：**已批准**
> 类型：金标整本评测门（承接 034a/a1/h 骨架 → 真件重译计分）
> 目标分支：建议 `feat/PLAN-051-gold-pharma-mqm`（亦可在 `main` 文档先行）
> 与 PLAN-050（UI/UX）并行，不阻塞

## 两道完成线

| 门 | 含义 | 判据 |
| --- | --- | --- |
| **工程门** | runner + scorer + 夹具可用 | `verify-plan-051.sh` 默认（无 LIVE）PASS |
| **产品门** | 可宣称 034 产品完成 | 真件四键过阈值，且 L/C/R 各类 ≥1 份 real |

R-01 已有 M2.5 真件（[PLAN-052](../PLAN-052-gold-real-fill/)）。产品门还要整本四键；工程门默认可绿。

## 文件索引

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 纲领 | [PLAN-051-gold-pharma-mqm.md](./PLAN-051-gold-pharma-mqm.md) | 目标、契约、Out of Scope、下一步 |
| 051a | [PLAN-051a-gold-runner.md](./PLAN-051a-gold-runner.md) | 整本执行器 + sha256 缓存 |
| 051b | [PLAN-051b-mqm-scorer.md](./PLAN-051b-mqm-scorer.md) | QC→MQM 四键 |
| 051c | [PLAN-051c-verify-gate.md](./PLAN-051c-verify-gate.md) | 门禁 + WT |

## 验收

```bash
bash scripts/verify-plan-051.sh
# LIVE（烧 GPU）：QYUNSLATION_PLAN051_LIVE=1 bash scripts/verify-plan-051.sh
```

Walkthrough：[WT-051-gold-pharma-mqm.md](../../walkthroughs/WT-051-gold-pharma-mqm.md)
