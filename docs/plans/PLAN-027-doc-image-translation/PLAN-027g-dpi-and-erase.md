# PLAN-027g 子计划：插图 300 DPI 回嵌与原文擦除残留

## 一、目标与解决痛点

1. **清晰度不足**：PDF 矢量默认 200 DPI 且 `VECTOR_MAX_PX=2400` 立刻压回；DOCX/PDF 位图按源像素嵌字，显示尺寸更大时被拉伸发糊。
2. **叠字**：OCR 框偏紧 + 文字带外整段回贴原图，把 `c` / `OL` 等残画贴回，译文叠在残留墨迹上。

---

## 二、详细技术规范

### 1. `ensure_display_dpi`（`doc_image_policy.py`）

```python
def ensure_display_dpi(img_bytes, width_pt, height_pt, *, target_dpi=300) -> bytes:
    # 有效 DPI = px * 72 / pt；仅低于 target 时 LANCZOS 上采样；已够清晰不缩小
```

默认 `QYUNSLATION_IMAGE_TARGET_DPI=300`。

接线：

- DOCX：`docx_image_overlay` 在 `translate_image_bytes` 前按 `occ.width_pt/height_pt` 升采样；回嵌仍用原 EMU。
- PDF 位图：升采样后译；尺寸变化走 `insert_image` overlay，禁止 `replace_image` 压回源像素。
- PDF 矢量：`VECTOR_CROP_DPI` 默认 300；`VECTOR_MAX_PX` 默认 4000。

### 2. 擦除残留（`image_translate.py`）

- `ERASE_PAD_PX` 默认 3：擦除前扩框。
- `FILL_BAND_PAD` 默认 4；`_text_mask_u8` 膨胀 3×3 / 2 次。
- 带外回贴排除文字 mask，禁止残字贴回。
- `_clear_ocr_leftovers`：擦后二次 RapidOCR，仍有墨迹则再填背景（上限 1 轮）。

不整框涂白，C10 仍守门。

---

## 三、验收标准

1. `VECTOR_CROP_DPI==300` 且 `VECTOR_MAX_PX>=4000`。
2. `ensure_display_dpi(100×50, 72×36pt)` → 约 300×150；已 300 DPI 不缩小。
3. 偏紧 OCR 框擦除后二次扫描 `detected_blocks==0`。
4. `verify-plan-027.sh` FAIL=0，含 026 回归。
