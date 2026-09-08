"""PLAN-030d Task 4：执行侧消费 manifest 并回写终态。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from qyunslation.structure import ManifestStore, PdfStructureScanner
from qyunslation.structure.models import ExecutionStatus, ObjectType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import pdf_image_translate  # noqa: E402
from pdf_image_translate import _structure_regions, translate_pdf_images  # noqa: E402

LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"

TRANSLATABLE = (ObjectType.FIGURE, ObjectType.IMAGE)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_MANIFEST_CACHE", str(tmp_path / "manifests"))


class _AlwaysTranslate:
    """只覆盖准入决策，其余能力（DPI 归一等）沿用真实 policy。"""

    def __init__(self):
        from qyunslation.extensions import doc_image_policy

        self._real = doc_image_policy

    def __getattr__(self, name):
        return getattr(self._real, name)

    def evaluate_image_candidate(self, *a, **k):
        class Decision:
            should_translate = True
            reason = "stub"

        return Decision()

    def evaluate_geometry(self, *a, **k):
        return True, "stub"


@pytest.fixture
def stub_translation(monkeypatch):
    """把 OCR/翻译换成确定性桩，隔离网络与模型。"""
    calls = []

    def fake_translate(png, to_lang):
        calls.append(to_lang)
        return png, 1, {}

    monkeypatch.setattr(pdf_image_translate, "_translate_via_local", fake_translate)
    monkeypatch.setattr(pdf_image_translate, "_load_policy", _AlwaysTranslate)
    monkeypatch.setattr(pdf_image_translate, "PDF_IMAGE_OVERLAY", True)
    return calls


def _planned(manifest):
    return [o for o in manifest.objects if o.type in TRANSLATABLE]


def test_structure_regions_returns_none_without_a_manifest():
    import pymupdf

    doc = pymupdf.open(LJAE)
    try:
        assert _structure_regions(None, 1, doc[0]) is None
    finally:
        doc.close()


def test_structure_regions_selects_only_this_pages_pending_objects():
    import pymupdf

    manifest = PdfStructureScanner().scan(LJAE)
    doc = pymupdf.open(LJAE)
    try:
        planned = _structure_regions(manifest, 2, doc[1])
    finally:
        doc.close()

    assert len(planned) == 1
    obj, rect = planned[0]
    assert obj.canvas_id == "page:2"
    assert rect.width > 0 and rect.height > 0


def test_regions_covered_by_bitmaps_are_left_to_the_bitmap_path():
    """同一张图不得既走位图 replace 又走矢量 overlay。"""
    import pymupdf

    manifest = PdfStructureScanner().scan(LJAE)
    doc = pymupdf.open(LJAE)
    try:
        claimed = 0
        for pno, page in enumerate(doc, start=1):
            exclude = [
                i["bbox"] for i in (page.get_image_info(xrefs=True) or []) if i.get("bbox")
            ]
            claimed += len(_structure_regions(manifest, pno, page, exclude))
    finally:
        doc.close()

    assert claimed == 1
    deferred = [o for o in _planned(manifest) if o.reason_code == "handled_by_bitmap_path"]
    assert len(deferred) == 5


def test_already_terminal_objects_are_not_replanned():
    import pymupdf

    manifest = PdfStructureScanner().scan(LJAE)
    for obj in _planned(manifest):
        obj.execution_status = ExecutionStatus.TRANSLATED

    doc = pymupdf.open(LJAE)
    try:
        assert _structure_regions(manifest, 2, doc[1]) == []
    finally:
        doc.close()


def test_execution_writes_back_terminal_states(tmp_path, stub_translation):
    src = tmp_path / "ljae439.pdf"
    shutil.copy(LJAE, src)
    manifest = PdfStructureScanner().scan(src)

    translate_pdf_images(src, to_lang="简体中文", structure_manifest=manifest)

    assert _planned(manifest), "sample must contain translatable objects"
    for obj in _planned(manifest):
        assert obj.execution_status is not ExecutionStatus.PENDING
        if obj.execution_status is not ExecutionStatus.TRANSLATED:
            assert obj.reason_code


def test_no_pending_objects_remain_after_execution(tmp_path, stub_translation):
    src = tmp_path / "nature.pdf"
    shutil.copy(NATURE, src)
    manifest = PdfStructureScanner().scan(src)

    translate_pdf_images(src, to_lang="简体中文", structure_manifest=manifest)

    pending = [o for o in _planned(manifest) if o.execution_status is ExecutionStatus.PENDING]
    assert pending == []


def test_execution_persists_the_updated_manifest(tmp_path, stub_translation):
    src = tmp_path / "ljae439.pdf"
    shutil.copy(LJAE, src)
    manifest = PdfStructureScanner().scan(src)

    translate_pdf_images(src, to_lang="简体中文", structure_manifest=manifest)
    stored = ManifestStore().get(manifest.document.source_sha256)

    assert stored is not None
    assert all(
        o.execution_status is not ExecutionStatus.PENDING
        for o in stored.objects
        if o.type in TRANSLATABLE
    )


def test_overlay_failure_is_recorded_as_failed_soft(tmp_path, stub_translation, monkeypatch):
    src = tmp_path / "ljae439.pdf"
    shutil.copy(LJAE, src)
    manifest = PdfStructureScanner().scan(src)

    import pymupdf

    def boom(self, *a, **k):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(pymupdf.Page, "insert_image", boom)

    translate_pdf_images(src, to_lang="简体中文", structure_manifest=manifest)

    states = {o.execution_status for o in _planned(manifest)}
    assert ExecutionStatus.FAILED_SOFT in states
    for obj in _planned(manifest):
        if obj.execution_status is ExecutionStatus.FAILED_SOFT:
            assert obj.reason_code == "overlay_failed"


def test_untranslatable_regions_are_skipped_with_a_reason(tmp_path, monkeypatch):
    src = tmp_path / "ljae439.pdf"
    shutil.copy(LJAE, src)
    manifest = PdfStructureScanner().scan(src)

    monkeypatch.setattr(
        pdf_image_translate, "_translate_via_local", lambda png, lang: (png, 0, {})
    )
    monkeypatch.setattr(pdf_image_translate, "_load_policy", _AlwaysTranslate)
    monkeypatch.setattr(pdf_image_translate, "PDF_IMAGE_OVERLAY", True)

    translate_pdf_images(src, to_lang="简体中文", structure_manifest=manifest)

    for obj in _planned(manifest):
        assert obj.execution_status is ExecutionStatus.EXPLICITLY_SKIPPED
        assert obj.reason_code in {
            "no_translatable_text",
            "not_reached",
            "handled_by_bitmap_path",
        }
    reasons = {o.reason_code for o in _planned(manifest)}
    assert "no_translatable_text" in reasons


def test_manifest_none_keeps_the_legacy_detection_path(
    tmp_path, stub_translation, monkeypatch
):
    """回滚路径：不传 manifest 时仍按 translatable_regions 逐页检测。"""
    import pdf_figure_crop

    src = tmp_path / "ljae439.pdf"
    shutil.copy(LJAE, src)

    seen = []
    original = pdf_figure_crop.translatable_regions

    def counting(page, **kwargs):
        result = original(page, **kwargs)
        seen.append(len(result))
        return result

    monkeypatch.setattr(pdf_figure_crop, "translatable_regions", counting)

    translate_pdf_images(src, to_lang="简体中文")

    assert len(seen) == 10, "legacy path must probe every page"
    # 6 处可译区中 5 处是位图，由策略 A 处理后从矢量候选里排除
    assert sum(seen) == 1


def test_manifest_path_does_not_redetect_regions(tmp_path, stub_translation, monkeypatch):
    import pdf_figure_crop

    src = tmp_path / "ljae439.pdf"
    shutil.copy(LJAE, src)
    manifest = PdfStructureScanner().scan(src)

    def fail_if_called(page, **kwargs):
        raise AssertionError("manifest path must not re-detect regions")

    monkeypatch.setattr(pdf_figure_crop, "translatable_regions", fail_if_called)

    translate_pdf_images(src, to_lang="简体中文", structure_manifest=manifest)

    assert all(o.execution_status is not ExecutionStatus.PENDING for o in _planned(manifest))
