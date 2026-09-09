"""PLAN-033：表格写出与图片 QC 接入生产后处理。"""
from __future__ import annotations

import importlib.util
import sys
import unicodedata
from pathlib import Path

import pymupdf

from qyunslation.structure.models import BoundingBox
from qyunslation.structure.role_fitter import QC_FONT_BELOW_TARGET
from qyunslation.structure.table_writeback import output_bbox, paint_cell


def test_output_bbox_shifts_dual_right_half():
    box = BoundingBox(x0=10, y0=20, x1=40, y1=35)
    shifted = output_bbox(box, 200, x_min_frac=0.5)
    assert shifted.x0 == 110
    assert shifted.x1 == 140
    assert shifted.y0 == 20


def test_paint_cell_keeps_searchable_vector_text(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    page.draw_rect(pymupdf.Rect(10, 10, 190, 40), color=(0, 0, 0), width=0.6)
    paint_cell(
        page,
        BoundingBox(x0=12, y0=12, x1=188, y1=38),
        "度普利尤单抗应答率",
        bold=True,
        font_size=9,
    )
    dest = tmp_path / "cell.pdf"
    doc.save(dest)
    doc.close()
    text = unicodedata.normalize("NFKC", pymupdf.open(dest)[0].get_text())
    assert "度普利尤单抗应答率" in text
    drawings = pymupdf.open(dest)[0].get_drawings()
    assert drawings  # 矢量框还在


def test_imgtr_details_include_object_qc():
    module = sys.modules.get("pdf_image_translate")
    if module is None or not hasattr(module, "detail_with_qc"):
        spec = importlib.util.spec_from_file_location(
            "pdf_image_translate",
            Path(__file__).resolve().parents[2] / "scripts/pdf_image_translate.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    detail = module.detail_with_qc(
        {"page": 1, "status": "vector_overlay"},
        {"object_qc": [QC_FONT_BELOW_TARGET], "dpi": 450},
    )
    assert detail["object_qc"] == [QC_FONT_BELOW_TARGET]
    assert detail["dpi"] == 450
    assert module.image_status_from_qc(detail["object_qc"]) == "TRANSLATED"


def test_docimg_post_installs_table_writeback():
    spec = importlib.util.spec_from_file_location(
        "apply_pdf2zh_docimg",
        Path(__file__).resolve().parents[2] / "scripts/apply-pdf2zh-docimg.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = """
                    if _dual and _dual != _mono:
                        out_dual = str(_qy_tr_pdf_img(_qy_Pimg(_dual)))
                    return out_mono, out_dual
"""
    patched, changed = module.install_table_post(source)
    assert changed is True
    assert "translate_pdf_tables" in patched
    assert "_qy_tbltr" in patched
    again, second = module.install_table_post(patched)
    assert second is False
