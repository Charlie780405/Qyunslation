# PLAN-052a：promote / inbox

> 状态：**已实现**
> 父计划：[PLAN-052](./PLAN-052-gold-real-fill.md)
> 验收：`pytest tests/gold/test_plan052_promote.py`

## 目标

将 catalog 条目从 synthetic 提升为 real：symlink 真 PDF → 重算 sha256 → 改 tags → `assert_catalog_complete`。

## Inbox

`$QYUNSLATION_PLAN034_GOLD_ROOT/inbox/{L,C,R}/<file>.pdf`（本机，不入库）。

## 类诚实性

- **R** 槽：来源登记 `kind=ctd-m2`（或 `--allow-kind ctd-m2`）
- **C** 槽：`protocol` / `clinical` 等；禁止把 protocol 写入 R
- 误标 → 抛错 / exit 2，不改 catalog

## 交付

| 路径 | 说明 |
| --- | --- |
| `qyunslation/gold/plan052_promote.py` | 核心 |
| `scripts/plan052-promote-gold.py` | CLI |
| `docs/gold/plan034/real-sources.json` | 登记表（无二进制） |
| `tests/gold/test_plan052_promote.py` | 夹具 |

## CLI

```bash
.venv/bin/python scripts/plan052-promote-gold.py \
  --entry R-01 --from /path/to/ctd-m2.pdf --kind ctd-m2
# 或从 inbox：--entry C-04 --from-inbox
```

## 判据

- synthetic→real 后 tags 含 `real`、无 `synthetic`；哈希匹配文件
- C 源 promote 到 R → 失败
- 不写入金标 PDF 到 git
