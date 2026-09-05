# PLAN-010a：盒去重叠

## 目标

OCR 层任意两盒不再纵向重叠，BabelDOC 不再有可切碎的重叠区。

## 改动

- `scripts/hpd_ocr.py`：`_deoverlap_boxes`、`_expand_boxes` 扫全部后继同列盒；debug `clamped` / `y1_before`
- `scripts/doc_profile.py`：`area < 400` 且 `len(text) < 12` 跳过微段落
- `scripts/test_hpd_deoverlap.py`

## 验收

`bash scripts/verify-plan-010.sh after-a`
