# PLAN-008b：行→段落聚合

在 `scripts/hpd_ocr.py`（本地包装，不改泰州 HPD `/parse`）于缩放之后、扩盒之前：

- `_cluster_columns`：x0 容差 8pt
- `_should_merge_lines`：行距 + 句末标点；`aggressive=False` 时短标签不并
- `_merge_lines_into_paragraphs`
- 扁盒扩高仍 1.2，已合并高盒 1.05

验收：`test_hpd_ocr_smoke.py` — `are enclosed.` 同块；表格不同列不粘连。
