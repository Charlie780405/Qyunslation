# PLAN-005c：图片嵌字

## Task C1 — HPD 检测 + 35b 译

复用 `hpd_ocr` 的 `_parse`/`_blocks`；CLI `scripts/hpd-overlay-image.py`。禁止 27b。

## Task C2 — standalone png/jpg

office 上传图片 → overlay 工作流 → `*.zh.png`。

## Task C3 — Word 内嵌图

`DocxTranslator` 对 `is_image_run` 抽图→嵌字→写回；失败保留原图。

## Task C4 — SLO

单张 A4 ≤90s。

## 回滚

`QYUNSLATION_IMAGE_OVERLAY=0`；docx 跳过图片。
