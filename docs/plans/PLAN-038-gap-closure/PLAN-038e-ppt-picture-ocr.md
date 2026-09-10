# PLAN-038e：PPT 嵌图 OCR（原 PLAN-034 另一半）

> 状态：**已完成**
> 父计划：[PLAN-038](./PLAN-038-gap-closure.md)
> 归属缺口：G-CAP-002；G-CAP-011=wontfix
> 验收：[WT-038e](../../walkthroughs/WT-038e-ppt-picture-ocr.md) / `bash scripts/verify-plan-038e.sh`

## 现状

`PPTXTranslator._overlay_images` 已调用 `translate_image_bytes`（SK-Q002）并回写 manifest 三态。文档仍写「PPT OCR out of scope」，属文档债。

## 交付

1. 加固/证明：`tests/structure/test_plan038e_pptx_picture_ocr.py`（嵌图 blob 被替换 + TRANSLATED）
2. `scripts/verify-plan-038e.sh`
3. 回写 WT-036 / WT-030g / 036 父纲领非目标表述

## 非目标

- SmartArt / Chart / OLE（G-CAP-011）

## 验收

- `bash scripts/verify-plan-038e.sh` PASS
- registry `G-CAP-002` = closed
