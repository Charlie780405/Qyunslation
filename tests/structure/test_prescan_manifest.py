"""PLAN-030d Task 3：预扫描从 manifest 派生计数，不再独立检测。"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure import ManifestStore, PdfStructureScanner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from doc_image_prescan import scan_pdf_tier3  # noqa: E402
from pdf_figure_crop import translatable_regions  # noqa: E402

from tests.structure.sample_paths import pind_ocr_sample, pind_sample, slide_sample

LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"
SLIDE = slide_sample()

requires_slide = pytest.mark.skipif(
    not SLIDE.is_file(), reason="slide sample lives outside the repo"
)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_MANIFEST_CACHE", str(tmp_path / "manifests"))


def _execution_regions(path: Path) -> int:
    doc = pymupdf.open(path)
    try:
        return sum(len(translatable_regions(page)) for page in doc)
    finally:
        doc.close()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        pytest.param(LJAE, 6, id="ljae439"),
        pytest.param(NATURE, 7, id="nature"),
        pytest.param(SLIDE, 12, id="slide", marks=requires_slide),
    ],
)
def test_prescan_matches_manifest_and_execution(path, expected):
    manifest = PdfStructureScanner().scan(path)
    result = scan_pdf_tier3(path)

    assert manifest.extensions["translatable_figure_count"] == expected
    assert result.translatable_count == expected
    assert _execution_regions(path) == expected


def test_caption_counts_are_unchanged_for_journals():
    result = scan_pdf_tier3(NATURE)

    assert result.figure_caption_count == 7
    assert result.table_caption_count == 3


def test_second_scan_reuses_the_cache_without_rescanning(monkeypatch):
    scan_pdf_tier3(NATURE)

    def fail_if_called(self, *args, **kwargs):
        raise AssertionError("cache hit must not trigger a rescan")

    monkeypatch.setattr(PdfStructureScanner, "scan", fail_if_called)

    assert scan_pdf_tier3(NATURE).translatable_count == 7


def test_stale_scanner_cache_is_rebuilt(monkeypatch):
    stale = PdfStructureScanner().scan(NATURE)
    stale.producer.version = "0.0.0"
    ManifestStore().put(stale)
    original_scan = PdfStructureScanner.scan
    calls = 0

    def counted_scan(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original_scan(self, *args, **kwargs)

    monkeypatch.setattr(PdfStructureScanner, "scan", counted_scan)

    result = scan_pdf_tier3(NATURE)

    assert calls == 1
    assert result.translatable_count == 7


def test_stale_cache_is_dropped_when_rebuild_is_truncated():
    stale = PdfStructureScanner().scan(NATURE)
    stale.producer.version = "0.0.0"
    ManifestStore().put(stale)
    digest = hashlib.sha256(NATURE.read_bytes()).hexdigest()

    result = scan_pdf_tier3(NATURE, max_pages=2)

    assert result.truncated is True
    cached = ManifestStore().get(digest)
    assert cached is None


def test_cache_entry_is_written_for_complete_scans():
    scan_pdf_tier3(NATURE)

    digest = hashlib.sha256(NATURE.read_bytes()).hexdigest()

    assert ManifestStore().get(digest) is not None


def test_truncated_scan_is_not_cached():
    result = scan_pdf_tier3(NATURE, max_pages=2)

    digest = hashlib.sha256(NATURE.read_bytes()).hexdigest()

    assert result.truncated is True
    assert ManifestStore().get(digest) is None


def test_abort_signal_truncates_and_skips_the_cache():
    result = scan_pdf_tier3(NATURE, should_abort=lambda: True)

    assert result.truncated is True
    assert result.translatable_count == 0


def test_encrypted_pdf_reports_an_error(tmp_path):
    target = tmp_path / "locked.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(target), encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()

    result = scan_pdf_tier3(target)

    assert result.error == "encrypted"
    assert result.translatable_count == 0


def test_unreadable_pdf_reports_an_error(tmp_path):
    target = tmp_path / "broken.pdf"
    target.write_bytes(b"%PDF-1.7\nnot really a pdf")

    result = scan_pdf_tier3(target)

    assert result.error
    assert result.translatable_count == 0


def test_corrupt_cache_entry_falls_back_to_a_fresh_scan():
    scan_pdf_tier3(NATURE)

    digest = hashlib.sha256(NATURE.read_bytes()).hexdigest()
    ManifestStore().path_for(digest).write_text("{ broken", encoding="utf-8")

    assert scan_pdf_tier3(NATURE).translatable_count == 7
