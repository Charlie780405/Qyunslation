# WT-030f：图片与 Poster 纵向闭环

## 一、实现概要

1. **028/029 门修复**：`structure/__init__.py` 对 `DocxStructureScanner` / `PdfStructureScanner` / `ImageStructureScanner` 懒加载，避免 pdf2zh Python 导入 `ingest` 时硬依赖 `python-docx`。
2. **扫描器**：[`scan_image.py`](../../qyunslation/structure/scan_image.py) — OCR 块 → `IMAGE` + `translatable_blocks`（bbox 必填）；`ContentProfile.POSTER` 或海报比例 → `POSTER` canvas + `POSTER_SECTION`。
3. **分块**：[`image_tiles.py`](../../qyunslation/structure/image_tiles.py) — 超大画布 tile 规划、内存预算与接缝 warning。
4. **画布**：[`canvases.py`](../../qyunslation/structure/canvases.py) — `h/w > 1.8` 或短边 > 4096px 标 `POSTER`。
5. **执行**：[`image_overlay_workflow.py`](../../qyunslation/workflow/image_overlay_workflow.py) 消费 manifest；译后 `put_execution` + `output_evidence`；`manifest=None` 仍走原路径。

## 二、验证

```bash
bash scripts/verify-plan-030f.sh
.venv/bin/python -m pytest tests/structure/test_scan_image.py -q --no-cov
```

## 三、非目标（仍归属后续）

- PPT 嵌图 `QY030-PPT-001` → 030g
- 跨格式对账 → 030h
- 像素金样人工门 → 030i
