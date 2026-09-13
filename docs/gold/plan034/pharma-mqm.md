# Pharma-MQM（PLAN-034a）

> version: **1.0.0**
> 用途：三类金标人工/半自动评测的错误分级；供基线报告与 034h 门禁引用。
> 结构门禁码复用既有 QC；本表补医药语义维度与级别。

## 级别

| 级别 | 含义 | 发布影响 |
| --- | --- | --- |
| **Critical** | 剂量/否定/禁忌错；参考文献被译；数字/单位/DOI 漂移；禁用译法命中 | 一律阻断发布 |
| **Major** | 硬性术语偏离；表格行列语义错；脚注漏译；关键实体错译 | 阻断发布（除非书面豁免） |
| **Minor** | 可接受的语序/语气/非关键同义 | 记入报告，不单独阻断 |

## 维度与门禁码映射

| ID | 级别 | 维度 | 现象 | 门禁码 / 检查点 |
| --- | --- | --- | --- | --- |
| PM-C1 | Critical | 剂量 | Q2W/Q4W 或 mg 剂量被改写 | `TABLE_DIGIT_DRIFT`；`text_sanitize` 剂量规则 |
| PM-C2 | Critical | 否定 | 否定极性翻转（无→有） | 人工 MQM；日后 034f |
| PM-C3 | Critical | 参考文献 | 参考文献整区被译 | 033d/h `PRESERVE`；`REF_GLUED_LEAK` |
| PM-C4 | Critical | 数字 | 百分比/日期/注册号漂移 | `TABLE_DIGIT_DRIFT`；`protect_tokens` |
| PM-C5 | Critical | 禁用译法 | 命中 forbidden_translation | 034d Concept；现阶段 glossary 抽查 |
| PM-M1 | Major | 术语 | 硬性术语未用指定译法 | SSOT `glossary_dict` 命中（034d0）；`DRUG_NAME_DRIFT` |
| PM-M2 | Major | 表格 | 行列语义错 / 并格 | `CELL_MERGE`；`COLUMN_CLUSTER_DRIFT` |
| PM-M3 | Major | 脚注 | 表注漏译 | `TABLE_FOOTNOTE_MISSING` |
| PM-M4 | Major | 残留 | 源文中文/拉丁残留 | `SOURCE_RESIDUE`；`PAGE_CJK_RESIDUE` |
| PM-M5 | Major | 实体 | 申办方/机构错译 | `ENTITY_MISMAP`（042） |
| PM-N1 | Minor | 语气 | 非关键同义或语序 | 人工 |
| PM-N2 | Minor | 版式 | 字号略低但可读 | `FONT_BELOW_TARGET`（画像可软） |

## 发布阈值（与 thresholds.toml 对齐）

- Critical 计数 = 0
- 硬性术语命中率 ≥ 0.98
- 禁用译法命中 = 0
- 数字/单位/DOI/参考文献保护通过率 = 1.0

## 变更

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| 1.0.0 | 2026-09-13 | PLAN-034a 初版 |
