"""PLAN-033c：嵌图后移到译文，双语只动右侧。"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pdf_image_translate  # noqa: E402
from pdf_image_translate import (  # noqa: E402
    _collect_xref_occurrences,
    _region_allowed,
    translate_pdf_images,
)


def _load_docimg():
    path = ROOT / "scripts" / "apply-pdf2zh-docimg.py"
    spec = importlib.util.spec_from_file_location("apply_pdf2zh_docimg", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_region_allowed_right_half_only():
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    try:
        assert _region_allowed((10, 10, 40, 40), page, page_no=0, x_min_frac=0.5, page_parity=None) is False
        assert _region_allowed((120, 10, 180, 40), page, page_no=0, x_min_frac=0.5, page_parity=None) is True
        assert _region_allowed((10, 10, 40, 40), page, page_no=1, x_min_frac=None, page_parity="even") is False
        assert _region_allowed((10, 10, 40, 40), page, page_no=2, x_min_frac=None, page_parity="even") is True
    finally:
        doc.close()


def test_collect_then_filter_drops_left_image(tmp_path):
    red = tmp_path / "red.png"
    green = tmp_path / "green.png"
    Image.new("RGB", (40, 40), (255, 0, 0)).save(red)
    Image.new("RGB", (40, 40), (0, 255, 0)).save(green)
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.insert_image(pymupdf.Rect(10, 30, 50, 70), filename=str(red))
    page.insert_image(pymupdf.Rect(140, 30, 180, 70), filename=str(green))
    occ = _collect_xref_occurrences(doc)
    kept = []
    for items in occ.values():
        for item in items:
            if _region_allowed(
                item["bbox"],
                doc[item["page"]],
                page_no=item["page"],
                x_min_frac=0.5,
                page_parity=None,
            ):
                kept.append(item["bbox"])
    doc.close()
    assert len(kept) == 1
    assert (kept[0][0] + kept[0][2]) / 2 > 100


def test_docimg_patch_moves_imgtr_after_babeldoc():
    stale = '''
        # _qy_imgtr: PDF 内嵌插图翻译前置（非扫描件）
        if not state.get("_hpd_retried"):
            if _qy_new and _qy_Pimg(_qy_new).is_file():
                file_path = _qy_new
        async for event in do_translate_async_stream(settings, file_path):
            pass

            if _mono is None and _dual is not None:
                _mono = _dual  # _qy_mono_fallback_dual
            # _qy_graphic_reinsert
            result_entry = {
                "mono": _mono,
            }
'''
    docimg = _load_docimg()
    updated, changed = docimg.apply(stale)
    assert changed
    assert docimg.SWAP_LINE not in updated
    assert "_qy_imgtr_post" in updated
    assert "x_min_frac" in updated
    assert "do_translate_async_stream(settings, file_path)" in updated
    assert "translate_pdf_tables" in updated
    assert "_qy_tbltr" in updated


def _half_hash(pdf: Path, *, left: bool) -> str:
    doc = pymupdf.open(pdf)
    try:
        page = doc[0]
        mid = page.rect.width / 2
        clip = pymupdf.Rect(0, 0, mid, page.rect.height) if left else pymupdf.Rect(
            mid, 0, page.rect.width, page.rect.height
        )
        return hashlib.sha256(page.get_pixmap(clip=clip, dpi=72).tobytes()).hexdigest()
    finally:
        doc.close()


def test_dual_left_render_hash_unchanged(tmp_path, monkeypatch):
    left_png = tmp_path / "left.png"
    right_png = tmp_path / "right.png"
    Image.new("RGB", (80, 80), (220, 30, 30)).save(left_png)
    Image.new("RGB", (80, 80), (30, 220, 30)).save(right_png)
    src = tmp_path / "dual.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=200)
    page.insert_image(pymupdf.Rect(20, 40, 160, 160), filename=str(left_png))
    page.insert_image(pymupdf.Rect(240, 40, 380, 160), filename=str(right_png))
    doc.save(src)
    doc.close()

    def fake_translate(png, to_lang):
        im = Image.open(io.BytesIO(png)).convert("RGB")
        painted = Image.new("RGB", im.size, (20, 40, 220))
        buf = io.BytesIO()
        painted.save(buf, format="PNG")
        return buf.getvalue(), 1, {}

    class _Always:
        def evaluate_image_candidate(self, *a, **k):
            class Decision:
                should_translate = True
                reason = "stub"

            return Decision()

        def evaluate_geometry(self, *a, **k):
            return True, "stub"

        def ensure_display_dpi(self, png, *a, **k):
            return png

    monkeypatch.setattr(pdf_image_translate, "_translate_via_local", fake_translate)
    monkeypatch.setattr(pdf_image_translate, "_load_policy", lambda: _Always())
    monkeypatch.setattr(pdf_image_translate, "PDF_IMAGE_OVERLAY", True)

    before_left = _half_hash(src, left=True)
    before_right = _half_hash(src, left=False)
    out = translate_pdf_images(src, to_lang="简体中文", x_min_frac=0.5)
    assert _half_hash(out, left=True) == before_left
    assert _half_hash(out, left=False) != before_right
