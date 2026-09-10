# PLAN-036：表格数字 policy 跨格式统一与续表金样

> 状态：**已完成**
> 验收：[WT-036](../../walkthroughs/WT-036-table-policy-unification.md) / `bash scripts/verify-plan-036.sh`
> 日期：2026-09-10
> 前置：[PLAN-035](../PLAN-035-table-execution-fidelity/PLAN-035-table-execution-fidelity.md)（已完成）
> 验收门：`bash scripts/verify-plan-036.sh`（编码后新增）

## 一、背景与缺口

PLAN-035 已在 **PDF 表格 scan + 执行** 路径交付 `table_cell_policy.py`（`PRESERVE` / `PROTECT_TOKENS` / `TRANSLATE`）与跨页续表扫描。但仓内仍有 **三处独立 numeric 规则**，行为可能漂移：

| 路径 | 现状 | 与 035 SSOT 关系 |
| --- | --- | --- |
| [`table_cell_policy.py`](../../../qyunslation/structure/table_cell_policy.py) | PDF 表格 scan + translate | **SSOT（035a）** |
| [`scan_docx.py`](../../../qyunslation/structure/scan_docx.py) `_numeric_preserve` | DOCX 单元格跳过翻译，**无** `translation_policy` 字段 | 重复实现 |
| [`md_tables.py`](../../../scripts/md_tables.py) `_is_preserve_cell` | 期刊 Markdown 管道表不进 LLM | 重复实现 |
| [`doc_image_policy.py`](../../../qyunslation/structure/doc_image_policy.py) `is_numeric_or_unit` | 图内 OCR 块语种/送译门控 | 语义相近、规则更宽 |

跨页续表：**合成** `continued-table.pdf` 已通过 035 单测；**ljae439 与 reference 目录无真实续表 PDF**，生产置信度不足。

父纲领 [PLAN-030](../PLAN-030-semantic-layout-translation/PLAN-030-semantic-layout-translation.md) 已收口；本计划为 **035 的自然延伸**，不扩 PLAN-034。

## 二、目标

1. **Policy SSOT**：`is_preserve_cell` / `classify_cell_policy` 成为表格与「纯数值块」判定的唯一实现；`md_tables`、`scan_docx`、`doc_image_policy` 改为引用或薄包装，删除重复正则。
2. **DOCX manifest 对齐 033g**：DOCX 表格 `TranslatableBlock` 写入 `translation_policy`（与 PDF 一致），numeric 单元格为 `PRESERVE`，不再靠特殊分支构造无 role/policy 的块。
3. **真实续表金样**：在 `tests/fixtures/structure/reference/` 纳入至少 1 份带 `Table N Continued` 的真实 PDF（或经用户批准的知识库样本），scan 硬断言：2 occurrence、`summary.table_count=1`、row 全局连续。
4. **文档收口**：更新 [WT-030-table](../../walkthroughs/WT-030-table-closure.md) 遗留项指向 035/036；036 WT 记录金样 SHA 与 verify 结果。

## 三、子计划矩阵

| 编号 | 文件 | 交付概要 | 顺序 |
| --- | --- | --- | --- |
| [036a](./PLAN-036a-policy-ssot-refactor.md) | policy SSOT  refactor | `md_tables` / `doc_image_policy` 收敛；parity 单测矩阵 | 1 |
| [036b](./PLAN-036b-docx-manifest-policy.md) | DOCX manifest | `scan_docx` 删 `_numeric_preserve`，写 `translation_policy` | 2 |
| [036c](./PLAN-036c-continued-table-gold.md) | 续表金样 | reference PDF + scan 金样断言 | 3 |
| [036d](./PLAN-036d-verify-docs-closure.md) | verify + WT | `verify-plan-036.sh`、WT-036、WT-030-table 补丁 | 4 |
| 036e（无独立文件） | 见下节 | 续表题注解析；DOCX 执行 policy；PPT 扫描 policy | 5 |

**建议实施顺序**：036a → 036b → 036c → 036d（a/b 可同 PR，c 依赖样本到位）。

### 036e 补充（已交付，记于 WT-036）

| 项 | 交付 |
| --- | --- |
| 续表题注 | `continued_table_caption_num`；Tailoring `Table continued` 可解析 |
| DOCX 执行 | `docx_table_exec.partition_docx_segments`；跳过 PRESERVE / PROTECT_TOKENS |
| PPT 扫描 | `scan_pptx` 表格块 `translation_policy` + `BlockRole.TABLE_CELL` |

表格可观测与 PPT 执行 policy 见 [PLAN-037](../PLAN-037-table-observability/PLAN-037-table-observability.md)（038b 补档）。

## 四、验证清单（编码后）

| # | 步骤 | 预期 |
| --- | --- | --- |
| V1 | `pytest tests/structure/test_plan036_*.py` | 全绿 |
| V2 | `pytest tests/structure/test_plan035_*.py` | 035 回归不退化 |
| V3 | `bash scripts/verify-plan-036.sh` | `SUMMARY: PASS fail=0` |
| V4 | `bash scripts/verify-plan-035.sh` | PASS |
| V5 | `bash scripts/verify-release.sh` | 必过门 PASS；033l 仍可为 BLOCKED |

## 五、非目标

- PDF 跨页续表 scan/exec 逻辑重写（035 已交付）
- 纯图片表 cell 网格、PPT picture OCR → [PLAN-038](../PLAN-038-gap-closure/PLAN-038-gap-closure.md) 038d/038e（不空开 034）
- DOCX/PPTX **跨页**续表 scan → G-CAP-009（038g）
- PLAN-034 复活
- 提交 `glossaries/auto-proper-nouns.csv`
- UI 展示 `TABLE_DIGIT_DRIFT`（可随 030ib 另开小改，本计划不强制）

## 六、风险与缓解

| 风险 | 缓解 |
| --- | --- |
| `is_numeric_or_unit` 与 `is_preserve_cell` 语义不完全等价 | 036a 建立 **parity 矩阵单测**；图内块保留 `is_numeric_or_unit` 为 documented wrapper |
| 真实续表 PDF 不可得 | 036c Task 0 样本门：无样本则纲领 BLOCKED，不 fake skip |
| md_tables 依赖 Hermes `lit_tables` | 只改 `_is_preserve_cell` 入口，不动提取链 |
| DOCX 执行器未读 `translation_policy` | 036b 仅 manifest；若 DOCX translate 路径存在，加最小断言或 EXPLICITLY_SKIPPED 文档说明 |

## 七、完成定义

- 三处重复 numeric 正则删除或变为单行 delegate
- DOCX 表格块带 `translation_policy`
- reference 续表 PDF 有 SHA256 登记（`catalog.v1.json` 或 sibling truth JSON）
- `verify-plan-036.sh` 纳入 `verify-release.sh`（可选 036d 任务）
- WT-036 与 WT-030-table 遗留项更新

## 八、批准门

用户确认本纲领及子计划后，开 `feat/PLAN-036-table-policy-unification` 编码；未经批准不改业务代码。
