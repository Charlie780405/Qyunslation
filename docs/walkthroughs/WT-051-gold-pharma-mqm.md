# WT-051：金标整本 Pharma-MQM 门

对应 [PLAN-051](../plans/PLAN-051-gold-pharma-mqm/PLAN-051-gold-pharma-mqm.md)。

## 执行摘要

承接 034a 契约，对 catalog **真件**走生产 `pdf2zh_next` 整本出稿，用已有 QC/034f/术语规则聚成四键；默认门禁不烧 GPU。034h 骨架门不变；**产品完成线改看本 WT 的产品门**。

## 两道门

| 门 | 命令 | 含义 |
| --- | --- | --- |
| 工程门 | `bash scripts/verify-plan-051.sh` | runner/scorer/夹具可用 |
| 产品门 | `QYUNSLATION_PLAN051_LIVE=1 bash scripts/verify-plan-051.sh` 且 L/C/R 各类有 real | 可宣称 034 产品完成 |

R-01 已为 GS101 临床综述 M2.5 real（→ [WT-052](./WT-052-gold-real-fill.md)）。产品门还要整本四键过阈值（`QYUNSLATION_PLAN051_LIVE=1`）。

## 用法

```bash
# 工程门（默认）
bash scripts/verify-plan-051.sh

# dry-run 看将跑哪些真件
.venv/bin/python scripts/plan051-run-gold.py --dry-run

# LIVE（可选 limit）
export QYUNSLATION_PLAN051_LIVE=1
export QYUNSLATION_PLAN051_LIMIT=1   # 可选
bash scripts/verify-plan-051.sh
```

环境变量：`QYUNSLATION_PLAN034_GOLD_ROOT`、`QYUNSLATION_PLAN051_OUT`（默认 `/tmp/plan051-out`）、`QYUNSLATION_OLLAMA_HOST`、`QYUNSLATION_PDF2ZH_CLI`。

**禁止** `git add` 金标 PDF 或 `/tmp/plan051-out` 译文。

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/gold/test_plan051*.py` | PASS |
| V2 | `bash scripts/verify-plan-051.sh` | `SUMMARY: PASS` |
| V3 | scorer 喂 skeleton | FAIL |
| V4 | LIVE 无 R 真件 | `product=BLOCKED` |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `docs/plans/PLAN-051-gold-pharma-mqm/*` | 纲领 + a/b/c |
| `qyunslation/gold/plan051_run.py` | 执行器 |
| `qyunslation/gold/plan051_score.py` | MQM 四键 |
| `scripts/plan051-*.py` / `verify-plan-051.sh` | 入口与门禁 |
| `tests/gold/test_plan051*.py` | 夹具 |
