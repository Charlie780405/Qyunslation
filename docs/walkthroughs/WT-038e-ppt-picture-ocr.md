# WT-038e：PPT 嵌图 OCR

日期：2026-09-10  
纲领：[PLAN-038e](../plans/PLAN-038-gap-closure/PLAN-038e-ppt-picture-ocr.md)

## 交付

- 证明既有 `PPTXTranslator._overlay_images` → `translate_image_bytes`（SK-Q002）会替换 media blob 并回写 `TRANSLATED`
- `tests/structure/test_plan038e_pptx_picture_ocr.py` / `scripts/verify-plan-038e.sh`
- SmartArt/Chart/OLE 保持 WONTFIX（G-CAP-011）

## 验收

```bash
bash scripts/verify-plan-038e.sh
```

## 关闭缺口

G-CAP-002
