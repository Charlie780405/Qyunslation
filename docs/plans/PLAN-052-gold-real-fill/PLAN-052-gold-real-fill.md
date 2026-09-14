# PLAN-052：金标真件补齐

> 状态：**已实现**（工程门绿；本机 R-01 M2.5 已 promote，`product_ready=yes`）
> 日期：2026-09-13
> 依赖：PLAN-034a1（物化/catalog）、PLAN-051（产品门各类 ≥1 real）
> 验收门：`bash scripts/verify-plan-052.sh`
> Walkthrough：[WT-052](../../walkthroughs/WT-052-gold-real-fill.md)

## 一句话

在不入库二进制的前提下，把 catalog 中 `synthetic` 槽 promote 为 `real`（symlink / DOCX→PDF + 重算哈希 + 标签）。方案/CDP 只进 C；CTD M2.5 综述只进 R。

## 现状

| 类 | real | synthetic | 说明 |
| --- | --- | --- | --- |
| L | 6 | 4 | 已满足产品门 |
| C | 7 | 3 | C-04/05 Protocol + C-06 方案 + C-07 CDP |
| R | 1 | 9 | R-01 = GS101 临床综述 M2.5 |

## 子计划

| ID | 交付 |
| --- | --- |
| [052a](./PLAN-052a-promote-inbox.md) | promote CLI + inbox + 登记表 + 类诚实性 |
| [052b](./PLAN-052b-c-protocol-candidates.md) | STREAM-AD / SOLO1 → C 槽 |
| [052c](./PLAN-052c-verify-gate.md) | verify 默认/严格 + WT |

## Out of Scope

- 整本重译 / 改 051 四键
- 伪造 CTD；Protocol/QnA/PIND 标成 R
- MedDRA、050 UI、053 Caddy
- 强制凑满 R×10（最低：各类 ≥1 real）

## 下一步

- 051 产品门：`QYUNSLATION_PLAN051_LIVE=1` 整本四键（本号只保证各类 ≥1 real）
- 其余 R 槽仍为 synthetic，不强制凑满 ×10
- **[053](../PLAN-053-saas-caddy-expose/)** SaaS 接线（Caddy 对外 `/api/v1`）

## 完成定义

- [x] 纲领 + a/b/c + README 索引
- [x] promote + pytest（禁误标 R）
- [x] C Protocol 候选登记
- [x] verify-052 默认 PASS；REQUIRE_R_REAL 时 R=0→BLOCKED
- [x] WT-052；051 回链
