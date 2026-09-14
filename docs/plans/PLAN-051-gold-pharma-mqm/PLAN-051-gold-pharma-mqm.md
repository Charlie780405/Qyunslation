# PLAN-051：金标整本 Pharma-MQM 门

> 状态：**已实现**（工程门；产品门待 052 真件）
> 依赖：PLAN-034a / 034a1 / 034f（契约与确定性 QA）；生产 CLI 同 033n
> 验收门：`bash scripts/verify-plan-051.sh`
> Walkthrough：[WT-051](../../walkthroughs/WT-051-gold-pharma-mqm.md)
> 并行：PLAN-050 UI/UX（不占用本号）

## 一句话

对 catalog 真件走生产 `pdf2zh_next` 整本出稿，把已有 QC/术语规则聚成 Pharma-MQM 四键，拒绝再用 `catalog-skeleton` 冒充发布通过。

## 承接契约（不新造阈值）

- 目录：[docs/gold/plan034/catalog.json](../../gold/plan034/catalog.json)
- 分级：[docs/gold/plan034/pharma-mqm.md](../../gold/plan034/pharma-mqm.md) 1.0.0
- 阈值：[docs/gold/plan034/thresholds.toml](../../gold/plan034/thresholds.toml)
- 判分：`evaluate_baseline_report`（[qyunslation/gold/plan034.py](../../../qyunslation/gold/plan034.py)）

计分默认只认 `tags` 含 `real`。合成件仅 opt-in 跑通管线，不进四键。

报告必须 `"mode": "full-retranslate"`。`catalog-skeleton` → **FAIL**。

## 子计划

| ID | 交付 |
| --- | --- |
| [051a](./PLAN-051a-gold-runner.md) | 整本执行器 + sha256 缓存 + run-manifest |
| [051b](./PLAN-051b-mqm-scorer.md) | QC/QA/术语 → 四键 |
| [051c](./PLAN-051c-verify-gate.md) | verify 默认/LIVE + WT |

## Out of Scope

- 050 UI；Caddy 对外 `/api/v1`；正式公司 IdP
- bge-m3 向量 TM；MedDRA；新翻译引擎
- 把合成 PDF 当 CSR/CTD M2 真件
- 金标 PDF / 译文二进制入库
- 改 034h 伞门骨架语义（034h 仍可跑 skeleton）

## 下一步（仅提示，不占号实施）

1. **[052](../PLAN-052-gold-real-fill/)** 真件补齐（尤其 R/CTD M2）→ 产品门才可能绿
2. **[053](../PLAN-053-saas-caddy-expose/)** SaaS 接线（Caddy / review 入队）
3. **[054](../PLAN-054-company-idp/)** 正式 IdP（Authentik）
4. **[055](../PLAN-055-tm-vector-embed/)** TM 向量（bge-m3 / 原 001g）

## 完成定义

- [x] 纲领 + 051a/b/c 文档落盘；`docs/plans/README.md` 索引
- [x] 051a runner + mock CLI 单测
- [x] 051b scorer + 夹具（脏/净/拒 skeleton）
- [x] `verify-plan-051.sh` 默认 PASS；LIVE 约定 BLOCKED/FAIL
- [x] WT-051；WT-034 注明产品完成改看 051 产品门
