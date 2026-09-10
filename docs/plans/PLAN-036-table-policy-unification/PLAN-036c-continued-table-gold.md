# PLAN-036c：真实跨页续表 reference 金样

> 状态：**已完成**（PLAN-036 / WT-036）
> 前置：035c 合成夹具已存在

## Task 0：样本门（编码前）

从以下来源择一 **≥1** 份 PDF：

1. 知识库 / Hermes attachments（需用户批准路径与入库）
2. 生产 anonymized 样本
3. 用户指定 Open Access 论文（含 `Table N Continued`）

**硬要求**：两页及以上；续页题注可解析为 `table_caption_num` + `is_continued_caption`。

无样本 → 036c **BLOCKED**，不得用合成件冒充 reference 金样。

## 交付

- `tests/fixtures/structure/reference/<name>.pdf`
- `tests/fixtures/structure/<name>.truth.json` 或扩展 `catalog.v1.json`（`origin: REFERENCE`）
- `tests/structure/test_plan036_continued_table_gold.py`：
  - `summary.table_count == 1`
  - 2+ `TableObject` 同 `semantic_id`，`semantic_occurrence_index` 递增
  - 续页 `min(row_index) > max(首 occurrence row_index)`

## 与 035 关系

- 保留合成 `continued-table.pdf`（GENERATED / catalog）
- reference 金样为 **额外** 硬断言，不替换合成件
