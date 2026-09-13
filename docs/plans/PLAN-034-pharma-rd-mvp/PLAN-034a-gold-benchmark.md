# PLAN-034a：金标语料与质量契约

> 状态：**已实现**（元数据 + MQM + 阈值；**034a1** 本机物化后 verify PASS）
> 父计划：[PLAN-034](./PLAN-034-pharma-rd-mvp.md)
> 依赖：无（复用 033 的 BLOCKED 机制）；样本补齐见 [PLAN-034a1](./PLAN-034a1-gold-materialize.md)
> 证据：[WT-034a](../../walkthroughs/WT-034a-gold-benchmark.md)
> 验收：`bash scripts/verify-plan-034a.sh`

## 目标

建立三类金标场景的样本目录、Pharma-MQM 错误分类、基线评测脚本与发布阈值；样本只记录目录、标签与哈希，**不提交真实资料**。

## 金标三类

| 类 | 范围 | 最低份数 |
| --- | --- | --- |
| L | 科研文献与综述 | 10 |
| C | 临床试验方案、IB、CSR | 10 |
| R | CTD Module 2 总结文档 | 10 |

## 交付

1. [docs/gold/plan034/catalog.json](../../gold/plan034/catalog.json)：清单（路径、标签、SHA-256、语言向、格式）；真实 PDF/DOCX 仅本机 `QYUNSLATION_PLAN034_GOLD_ROOT`。
2. [pharma-mqm.md](../../gold/plan034/pharma-mqm.md)：Critical / Major / Minor；医药专属维度。
3. [thresholds.toml](../../gold/plan034/thresholds.toml) + `evaluate_baseline_report`。
4. `scripts/plan034a-baseline.py`：provenance + ready 条目巡检（本期不整本重译）。
5. `scripts/verify-plan-034a.sh`：缺样本 **BLOCKED**（禁止 skip 冒充通过）。
6. [PLAN-034a1](./PLAN-034a1-gold-materialize.md)：`plan034a-materialize-gold.py` 真件 symlink + 合成占位；catalog `real`/`synthetic`。

## 判据

- 清单 ≥30 条且三类各 ≥10 槽位；**ready+文件** 三类各 ≥10 才 PASS，否则 BLOCKED。
- `tags` 可含 `real` 或 `synthetic`；门禁不区分；034h 可只认真件。
- Pharma-MQM `version=1.0.0`，可被 034h 引用。
- 基线报告可复现（模型、提示词/术语指纹、git HEAD）。

## Out of Scope

- 把金标原文提交进 git
- 训练或微调模型
- 实现审校 UI（→ 034g）

## 完成定义

- [x] 样本清单 + MQM + 阈值文档合入
- [x] verify 缺样本 BLOCKED
- [x] 基线评测骨架 + WT-034a
- [x] 034a1 本机物化后 verify PASS（见 PLAN-034a1）