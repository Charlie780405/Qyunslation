# PLAN-052：金标真件补齐

> 状态：**已实现**（工程门；产品门待 CTD M2 入 inbox）
> 类型：synthetic→real promote / inbox，解锁 051 产品门前置
> 依赖：PLAN-034a1、PLAN-051
> 与 PLAN-050 / 051 并行

## 两道完成线

| 门 | 含义 | 判据 |
| --- | --- | --- |
| **工程门** | promote 工具 + 夹具 + C 候选登记 | `verify-plan-052.sh` 默认 PASS |
| **产品条件** | L/C/R 各类 ≥1 `real`（尤其 R） | `QYUNSLATION_PLAN052_REQUIRE_R_REAL=1` |

本机 R-01 = GS101 M2.5 → `product_ready=yes`。051 产品门还要整本四键（`PLAN051_LIVE`）。

## 文件索引

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 纲领 | [PLAN-052-gold-real-fill.md](./PLAN-052-gold-real-fill.md) | 目标与 Out of Scope |
| 052a | [PLAN-052a-promote-inbox.md](./PLAN-052a-promote-inbox.md) | promote / inbox |
| 052b | [PLAN-052b-c-protocol-candidates.md](./PLAN-052b-c-protocol-candidates.md) | C 类 Protocol 候选 |
| 052c | [PLAN-052c-verify-gate.md](./PLAN-052c-verify-gate.md) | 门禁 |

## 验收

```bash
bash scripts/verify-plan-052.sh
# 强制产品条件：QYUNSLATION_PLAN052_REQUIRE_R_REAL=1 bash scripts/verify-plan-052.sh
```

Walkthrough：[WT-052-gold-real-fill.md](../../walkthroughs/WT-052-gold-real-fill.md)
