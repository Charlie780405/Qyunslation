# WT-027 文档内嵌图片翻译

## 交付摘要

实现 PLAN-027：上传预扫描 + DOCX DrawingML 实例解耦嵌字 + PDF 位图/矢量双策略原位回嵌；027f 引擎可观测；027g 300 DPI 回嵌与擦除残留清理。

## 关键变更

| 路径 | 说明 |
| --- | --- |
| `qyunslation/extensions/doc_image_policy.py` | 几何/语种/数字判定 + `ensure_display_dpi` |
| `qyunslation/extensions/docx_image_overlay.py` | DrawingML 枚举 + 升采样后嵌字 |
| `qyunslation/extensions/image_translate.py` | Alpha、OCR 引擎、扩框擦除、二次清残留 |
| `scripts/pdf_figure_crop.py` | 矢量默认 300 DPI / MAX_PX 4000 |
| `scripts/pdf_image_translate.py` | 升采样 + overlay；跨 venv sidecar |
| `scripts/verify-plan-027.sh` | 含 §8d/§8e |
| SK-Q002 | 铁律 23–37 |

## PLAN-027g：300 DPI 与擦除残留

| 项 | 说明 |
| --- | --- |
| DPI | `ensure_display_dpi` 仅上采样到 300；矢量 `VECTOR_CROP_DPI=300` |
| 擦除 | `ERASE_PAD_PX=3`、`FILL_BAND_PAD=4`；带外回贴避文字 mask |
| 残留 | `_clear_ocr_leftovers` 擦后二次 OCR 再填 |

## 验收

```bash
bash scripts/verify-plan-027.sh
```

预期：`FAIL=0`，含 §8e DPI/残留、回归 026。

## 部署

```bash
systemctl --user restart qyunslation-office.service
systemctl --user restart pdf2zh.service
```

部署 commit：`a928380`
