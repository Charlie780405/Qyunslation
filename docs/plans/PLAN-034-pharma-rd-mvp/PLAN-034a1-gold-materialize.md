# PLAN-034a1：金标本机补齐（真件 + 合成占位）

> 状态：**已实现**
> 父计划：[PLAN-034a](./PLAN-034a-gold-benchmark.md)
> 依赖：PLAN-034a（catalog / assert / verify 契约）
> 证据：[WT-034a](../../walkthroughs/WT-034a-gold-benchmark.md)（含 a1 物化）
> 验收：`bash scripts/verify-plan-034a.sh` → `SUMMARY: PASS`（本机已物化）

## 目标

在不入库二进制的前提下，用本机真 PDF 优先、缺口确定性合成 PDF，补齐 L/C/R 各 ≥10 条 `ready`，更新 catalog 哈希与 `real`/`synthetic` 标签，使 034a 门禁从 BLOCKED 变为 PASS。

## 交付

1. `qyunslation/gold/synthesize.py`：确定性 1 页 A4 占位 PDF（固定元数据 + 稳定 `/ID`）。
2. `scripts/plan034a-materialize-gold.py`：真件 `symlink` + 合成写入 `GOLD_ROOT`，重写 `catalog.json`，调用 `assert_catalog_complete`。
3. `docs/gold/plan034/catalog.json`：30 条全部 `ready`；每条恰一标 `real` 或 `synthetic`。
4. `tests/gold/test_plan034a1_materialize.py`：哈希稳定 + tmp 物化完备 + 标签互斥。

## 本机计数（物化后）

| 类 | ready | real | synthetic |
| --- | --- | --- | --- |
| L | 10 | 6 | 4 |
| C | 10 | 3 | 7 |
| R | 10 | 0 | 10 |
| 合计 | 30 | 9 | 21 |

C 真件含临床 QnA / PIND（非严格 CSP）；R 无本机 CTD M2 真件，全部合成。CSP 仅有 docx 时本期不转换，走合成。

## 用法

```bash
.venv/bin/python scripts/plan034a-materialize-gold.py
# --dry-run 只打印映射；--gold-root / --catalog 可覆盖路径
bash scripts/verify-plan-034a.sh   # 期望 SUMMARY: PASS
```

**禁止** `git add` `qyunslation-gold/` 或任何金标 PDF。

## 034h 换真件

`tags` 含 `synthetic` 的条目可在 034h 用真件替换：更新 symlink/文件 → 重算 sha256 → 改 `tags` 为 `real`（及业务标签）。`assert_catalog_complete` **不**区分 real/synthetic。

## Out of Scope

- MedDRA / 整本重译 / 034b–d 产品代码
- 把幻灯或 PIND 误标为 CTD M2
- 强制用户提供 28 份真 CSR/M2

## 完成定义

- [x] 物化脚本 + 合成模块
- [x] catalog 30 ready + 标签
- [x] pytest + verify 扩展
- [x] 本机 `assert_catalog_complete` / verify PASS
