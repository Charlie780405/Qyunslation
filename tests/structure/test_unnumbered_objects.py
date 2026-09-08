"""PLAN-030d Task 2：无编号可译对象建模。"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.models import ExecutionStatus, ObjectType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from pdf_figure_crop import _drop_nested, translatable_regions  # noqa: E402
from tests.structure.sample_paths import slide_sample

LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"
SLIDE = slide_sample()

requires_slide = pytest.mark.skipif(
    not SLIDE.is_file(), reason="slide sample lives outside the repo"
)


def _images(manifest):
    return [o for o in manifest.objects if o.type is ObjectType.IMAGE]


def _execution_region_count(path: Path) -> int:
    doc = pymupdf.open(path)
    try:
        return sum(len(translatable_regions(page)) for page in doc)
    finally:
        doc.close()


@pytest.fixture(scope="module")
def ljae_manifest():
    return PdfStructureScanner().scan(LJAE)


@pytest.fixture(scope="module")
def nature_manifest():
    return PdfStructureScanner().scan(NATURE)


def test_nested_duplicate_regions_are_dropped():
    parent = pymupdf.Rect(52, 80, 548, 407)
    nested = pymupdf.Rect(52, 80, 548, 212)
    separate = pymupdf.Rect(52, 500, 300, 700)

    kept = _drop_nested([nested, parent, separate])

    assert parent in kept
    assert nested not in kept
    assert separate in kept


def test_dedupe_keeps_merely_overlapping_regions():
    left = pymupdf.Rect(0, 0, 100, 100)
    right = pymupdf.Rect(80, 0, 180, 100)

    assert len(_drop_nested([left, right])) == 2


def test_dedupe_is_idempotent():
    rects = [pymupdf.Rect(0, 0, 100, 100), pymupdf.Rect(10, 10, 50, 50)]

    once = _drop_nested(rects)

    assert _drop_nested(once) == once


def test_ljae_page2_reports_one_region_not_a_nested_pair():
    doc = pymupdf.open(LJAE)
    try:
        assert len(translatable_regions(doc[1])) == 1
    finally:
        doc.close()


def test_unnumbered_regions_become_image_objects_not_figures(ljae_manifest):
    images = _images(ljae_manifest)

    assert len(images) == 1
    assert ljae_manifest.summary.figure_count == 5


def test_image_objects_never_claim_a_figure_number(ljae_manifest):
    for image in _images(ljae_manifest):
        assert image.semantic_scope == "unnumbered"
        assert image.semantic_id is not None
        assert image.semantic_id.startswith("image:page:")
        assert not image.semantic_id.startswith("figure:")


def test_image_objects_carry_shared_detector_evidence(ljae_manifest):
    for image in _images(ljae_manifest):
        detectors = {e.detector for e in image.detector_evidence}
        assert "translatable_regions" in detectors
        assert image.planned_action == "ocr_overlay"
        assert image.execution_status is ExecutionStatus.PENDING


def test_captioned_document_produces_no_spurious_image_objects(nature_manifest):
    assert _images(nature_manifest) == []
    assert nature_manifest.summary.figure_count == 7
    assert nature_manifest.summary.table_count == 3


@requires_slide
def test_slide_regions_enter_the_manifest_without_fake_numbers():
    manifest = PdfStructureScanner().scan(SLIDE)

    assert manifest.summary.figure_count == 0
    assert len(_images(manifest)) == 12
    assert manifest.summary.object_counts.get("IMAGE") == 12


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(LJAE, id="ljae439"),
        pytest.param(NATURE, id="nature"),
        pytest.param(SLIDE, id="slide", marks=requires_slide),
    ],
)
def test_manifest_translatable_count_matches_execution(path):
    manifest = PdfStructureScanner().scan(path)

    assert manifest.extensions["translatable_figure_count"] == _execution_region_count(path)


def test_image_object_ids_are_stable_across_scans():
    first = {o.object_id for o in _images(PdfStructureScanner().scan(LJAE))}
    second = {o.object_id for o in _images(PdfStructureScanner().scan(LJAE))}

    assert first == second
