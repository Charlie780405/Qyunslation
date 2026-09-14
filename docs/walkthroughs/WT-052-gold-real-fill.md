# WT-052：金标真件补齐

对应 [PLAN-052](../plans/PLAN-052-gold-real-fill/PLAN-052-gold-real-fill.md)。解锁 [WT-051](./WT-051-gold-pharma-mqm.md) 产品门的前置是 **R 类 ≥1 份 real**。

## 执行摘要

promote/inbox 把 catalog 的 `synthetic` 槽换成真件 symlink（或 DOCX→PDF）。类诚实性：方案/CDP 只进 **C**；CTD M2.5 综述只进 **R**。本机三份景行 DOCX 已从 `docs/Resources/` promote：`L=6 C=7 R=1 product_ready=yes`。

## 景行 IND 例文（同事补充）

| 文件（Windows，不入库） | 槽 | kind |
| --- | --- | --- |
| GS101 注射液 1 期临床研究方案-V1.0-20251023clean.docx | C-06 | protocol |
| GS101 注射液临床开发计划-V1.0-20251023-Final-Clean.docx | C-07 | cdp |
| GS101 注射液临床综述-V1.0-20251023-Final-Clean.docx（M2.5） | R-01 | ctd-m2 |

登记表：[docs/gold/plan034/real-sources.json](../gold/plan034/real-sources.json)。

本机源在 `docs/Resources/`（gitignore，不入库）：

```bash
.venv/bin/python scripts/plan052-promote-gold.py --entry C-06 \
  --from docs/Resources/GS101注射液1期临床研究方案-V1.0-20251023clean.docx
.venv/bin/python scripts/plan052-promote-gold.py --entry C-07 \
  --from docs/Resources/GS101注射液临床开发计划-V1.0-20251023-Final-Clean.docx
.venv/bin/python scripts/plan052-promote-gold.py --entry R-01 \
  --from docs/Resources/GS101注射液临床综述-V1.0-20251023-Final-Clean.docx
```

DOCX 经 LibreOffice 转 PDF 后写入 `GOLD_ROOT`，禁止 `git add` 二进制。

已 promote：C-04 STREAM-AD、C-05 SOLO1-2、C-06 方案、C-07 CDP、R-01 M2.5。

## 验证

```bash
bash scripts/verify-plan-052.sh
# 强制产品条件（无 M2.5 时 BLOCKED）
QYUNSLATION_PLAN052_REQUIRE_R_REAL=1 bash scripts/verify-plan-052.sh
```

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/gold/test_plan052_promote.py` | PASS |
| V2 | 默认 verify | `SUMMARY: PASS`；本机打印 `product_ready=yes` |
| V3 | Protocol/CDP promote 到 R | 失败 |
| V4 | `REQUIRE_R_REAL=1` | 本机 PASS；R=0 时 BLOCKED |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/gold/plan052_promote.py` | promote + 类诚实 + DOCX→PDF |
| `scripts/plan052-promote-gold.py` | CLI |
| `docs/gold/plan034/real-sources.json` | 例文登记 |
| `scripts/verify-plan-052.sh` | 工程/产品门 |
| `tests/gold/test_plan052_promote.py` | 夹具 |
