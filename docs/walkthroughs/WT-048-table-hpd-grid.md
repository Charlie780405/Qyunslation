# WT-048 表格 HPD 网格保真

## 摘要

借鉴 Hermes HPD：视觉解析出逻辑网格，文字层出内容并对齐落笔；`geometry_center` 一律不落笔；假阳性表交图片链；失败走字号归一。沉淀 SK-Q009。

## 改动要点

- `table_grid_hpd.py`：HPD 客户端、LaTeX 剥离、折行合并、磁盘缓存
- `table_structure.py`：`structure_table_ex` / `align_hpd_grid` / 空隙投影；废弃列簇合并
- `table_qc.py`：三闸门 + `assert_grid_source_safe`
- `tables.py`：`_expand_region_left`
- `pdf_table_translate.py` / `pdf_table_normalize.py`：降级阶梯与角色分带字号
- SK-Q009 + registry + error-signatures

## 验收

```bash
bash scripts/verify-plan-048.sh
# 可选实样：
# QYUNSLATION_PLAN048_SAMPLE=/path/to/ljae439.pdf bash scripts/verify-plan-048.sh
bash scripts/deploy-translate-stack.sh
```

## 判据

- 表1：4 列，碎片合成 `Tralokinumab Q2W (N=130)`
- 表2：`NOT_A_TABLE`，不涂改图注
- 表3：nAb 与浓度分列；左边界尽量含 Dose
- HPD 错字不进译文
