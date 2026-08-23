# WT-005c 图片嵌字

**日期：** 2026-08-23  
**状态：** 已部署代码

## 变更

| 项 | 内容 |
| --- | --- |
| `image_translate.py` | HPD 检测 + **35b**（禁 27b）+ inpaint 嵌字 |
| CLI | `scripts/hpd-overlay-image.py` |
| 工作流 | `image_overlay`（png/jpg）；Word 内嵌图 `_overlay_embedded_images` |
| 失败 | 单图失败保留原图 |

## 回滚

`QYUNSLATION_IMAGE_OVERLAY=0` 后重启 office。
