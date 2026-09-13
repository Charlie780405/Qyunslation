# WT-034a：金标语料与质量契约

对应 [PLAN-034a](../plans/PLAN-034-pharma-rd-mvp/PLAN-034a-gold-benchmark.md) / [PLAN-034a1](../plans/PLAN-034-pharma-rd-mvp/PLAN-034a1-gold-materialize.md)。

## 执行摘要

落地三类金标 **元数据清单**（`docs/gold/plan034/catalog.json`，30 条全部 `ready`）、Pharma-MQM 1.0.0、发布阈值，以及 `verify-plan-034a.sh`。真实 PDF **不入库**；本机默认根 `/home/dev/qyunslation-gold/plan034`。

**PLAN-034a1** 用真件 symlink + 确定性合成占位补齐本机文件后，门禁从 BLOCKED 变为 PASS。catalog `tags` 含恰好一个 `real` 或 `synthetic`。

## 本机寻址与物化

```bash
export QYUNSLATION_PLAN034_GOLD_ROOT=/home/dev/qyunslation-gold/plan034   # 可选
.venv/bin/python scripts/plan034a-materialize-gold.py
# 布局：{GOLD_ROOT}/L|C|R/<relpath>
```

真件优先（存在才挂；缺失自动合成，脚本 `WARN skip missing`）：

| id | relpath | 来源（不入库） |
| --- | --- | --- |
| L-033-elsevier-ad | `L/plan033-elsevier-ad.pdf` | hermes Elsevier 附件 |
| L-ljae439 | `L/ljae439.pdf` | 作业目录 / fixtures |
| L-nature-comm-53384 等 | `L/*.pdf` | fixtures / 外刊附件 |
| C-qx027n-qna / C-fda-pind* | `C/*.pdf` | 临床问答 / PIND（非严格 CSP） |
| L-07… / C-04… / R-01… | 合成标题页 | `tags: synthetic` |

本机计数约：**real 9 / synthetic 21**（L 6+4，C 3+7，R 0+10）。

## 解除 BLOCKED（a1 后）

1. 跑 `plan034a-materialize-gold.py`（或手工保证三类各 ≥10 ready+哈希匹配）。
2. `bash scripts/verify-plan-034a.sh` → `SUMMARY: PASS`。
3. 034h 换真件：替换文件、更新 sha 与 `tags`；勿提交二进制。

## 基线脚本

```bash
.venv/bin/python scripts/plan034a-baseline.py
# 报告默认 /tmp/plan034a-baseline-<date>.md；完备性不足 exit 2
```

本期不做整本重译；有 `artifact_mono` 才记探针，否则 `SKIPPED_NO_ARTIFACT`。

## 验证

| # | 项 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/gold/test_plan034a_catalog.py tests/gold/test_plan034a1_materialize.py` | PASS |
| V2 | `verify-plan-034a.sh`（本机已物化） | PASS |
| V3 | `git status` 无 `qyunslation-gold/` 二进制 | 干净 |

## 变更明细

| 路径 | 摘要 |
| --- | --- |
| `qyunslation/gold/plan034.py` | catalog / hash / thresholds |
| `qyunslation/gold/synthesize.py` | 确定性合成 PDF |
| `docs/gold/plan034/*` | catalog、MQM、thresholds、README |
| `scripts/plan034a-materialize-gold.py` | 真件+合成物化 |
| `scripts/plan034a-baseline.py` | 基线骨架 |
| `scripts/verify-plan-034a.sh` | 金标门 + a1 文件存在性 |
| `tests/gold/test_plan034a1_materialize.py` | 哈希/物化/标签 |
