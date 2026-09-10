# PLAN-036a：Policy SSOT refactor

> 状态：**已完成**（PLAN-036 / WT-036）

## 改

| 文件 | 动作 |
| --- | --- |
| [`table_cell_policy.py`](../../../qyunslation/structure/table_cell_policy.py) | 必要时导出 `is_numeric_or_unit` 兼容别名（documented wrapper） |
| [`scripts/md_tables.py`](../../../scripts/md_tables.py) | `_is_preserve_cell` → `from qyunslation.structure.table_cell_policy import is_preserve_cell` |
| [`doc_image_policy.py`](../../../qyunslation/structure/doc_image_policy.py) | `is_numeric_or_unit` delegate 至 `is_preserve_cell`（或共享子函数）；保留对外签名 |
| [`scan_docx.py`](../../../qyunslation/structure/scan_docx.py) | 删除 `_NUMERIC_CELL` / `_numeric_preserve` 本地定义（policy 写入留 036b） |

## 测试

- 新增 `tests/structure/test_plan036_policy_parity.py`：
  - 矩阵：`42`、`42.3%`、`N/A`、`n=120`、`Age 42 years`、`Endpoint`
  - 断言 `is_preserve_cell` / `classify_cell_policy` / （wrapper）`is_numeric_or_unit` 预期一致或 documented 差异
- `tests/structure/test_plan029*.py` 或 md_tables 相关回归（若有）

## 验收

- 三文件中无独立 `_PRESERVE_CELL` / `_NUMERIC_CELL` 重复正则（`table_cell_policy` 除外）
- parity 单测全绿
