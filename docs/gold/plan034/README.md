# PLAN-034 金标语料（元数据入库，二进制不入库）

## 布局

```text
docs/gold/plan034/           # 本目录：catalog / MQM / thresholds（git）
QYUNSLATION_PLAN034_GOLD_ROOT 或默认 /home/dev/qyunslation-gold/plan034
  L/   # 文献与综述
  C/   # 方案 / IB / CSR（及本机可挂的临床/监管 PDF）
  R/   # CTD Module 2（本机无真件时为合成占位）
```

## 物化（PLAN-034a1）

```bash
.venv/bin/python scripts/plan034a-materialize-gold.py
```

- 真件：对本机已存在路径做 `symlink`，catalog `tags` 含 `real`。
- 缺口：确定性合成 PDF，`tags` 含 `synthetic`。
- 重复跑幂等；**勿**把 `GOLD_ROOT` 二进制 `git add`。
- 门禁：`assert_catalog_complete` 不区分 real/synthetic；034h 可用 `tags` 过滤仅真件。

本机物化后大致：**L 6 real + 4 synthetic；C 3 real + 7 synthetic；R 10 synthetic**。

## 放置 / 换真件

1. `export QYUNSLATION_PLAN034_GOLD_ROOT=/home/dev/qyunslation-gold/plan034`（可选，有默认）。
2. 文件路径 `{GOLD_ROOT}/{class}/{relpath}`，与 [catalog.json](./catalog.json) 的 `relpath` / `sha256` 一致。
3. 用真件替换合成后：更新文件 → 重算 sha → `tags` 改为含 `real`（去掉 `synthetic`）。

## 种子（真件保留原文件名）

| id | class | 说明 |
| --- | --- | --- |
| L-033-elsevier-ad | L | PLAN-033 11 页文献样 |
| L-ljae439 | L | 表3 保真用文献 PDF |

## 相关

- Pharma-MQM：[pharma-mqm.md](./pharma-mqm.md)
- 阈值：[thresholds.toml](./thresholds.toml)
- 加载器：`qyunslation.gold.plan034`
- 子计划：[PLAN-034a1](../../plans/PLAN-034-pharma-rd-mvp/PLAN-034a1-gold-materialize.md)
