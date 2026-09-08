"""PLAN-030d Task 5：Tier-3 错误如实上报，不得伪装成零结果。"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.models import IssueSeverity, PipelineStage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import doc_image_prescan  # noqa: E402
from doc_image_prescan import format_tier3_summary, scan_pdf_tier3  # noqa: E402

NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"
NO_FIGURES = "未检测到需要嵌字的插图。"


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_MANIFEST_CACHE", str(tmp_path / "manifests"))


@pytest.mark.parametrize(
    "error",
    ["encrypted", "pymupdf_missing", "pdf_figure_crop_missing", "some crash", "boom"],
)
def test_errors_never_read_as_no_illustrations(error):
    text = format_tier3_summary({}, vector_count=0, table_count=0, error=error)

    assert text != NO_FIGURES
    assert "未检测到" not in text


def test_encrypted_has_its_own_wording():
    text = format_tier3_summary({}, vector_count=0, table_count=0, error="encrypted")

    assert "加密" in text


def test_missing_dependency_has_its_own_wording():
    text = format_tier3_summary({}, vector_count=0, table_count=0, error="pymupdf_missing")

    assert "组件不可用" in text


def test_unknown_error_is_shown_verbatim():
    text = format_tier3_summary({}, vector_count=0, table_count=0, error="weird failure")

    assert "weird failure" in text


def test_error_can_come_from_the_prescan_entry():
    text = format_tier3_summary({"tier3_error": "encrypted"}, vector_count=0, table_count=0)

    assert "加密" in text


def test_genuine_zero_still_reports_no_illustrations():
    assert format_tier3_summary({}, vector_count=0, table_count=0) == NO_FIGURES


def test_error_takes_precedence_over_stale_counts():
    text = format_tier3_summary(
        {}, vector_count=7, table_count=3, error="encrypted", translatable_count=7
    )

    assert "加密" in text
    assert "7 张" not in text


def test_truncation_wording_is_unaffected():
    text = format_tier3_summary(
        {},
        vector_count=7,
        table_count=3,
        truncated=True,
        pages_scanned=40,
        figure_caption_count=7,
        table_caption_count=3,
        translatable_count=7,
    )

    assert "仅扫描前 40 页" in text
    assert "未检测到" not in text


def test_encrypted_pdf_end_to_end_reports_the_error(tmp_path):
    target = tmp_path / "locked.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(target), encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()

    result = scan_pdf_tier3(target)
    text = format_tier3_summary({}, vector_count=0, table_count=0, error=result.error)

    assert result.error == "encrypted"
    assert text != NO_FIGURES


def test_missing_pymupdf_is_reported(monkeypatch, tmp_path):
    target = tmp_path / "doc.pdf"
    target.write_bytes(NATURE.read_bytes())

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def blocked(name, *args, **kwargs):
        if name == "pymupdf":
            raise ImportError("no pymupdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    result = scan_pdf_tier3(target)

    assert result.error == "pymupdf_missing"


def test_page_level_failure_is_recorded_as_an_issue(monkeypatch):
    import qyunslation.structure.scan_pdf as scan_mod

    calls = {"n": 0}
    real = scan_mod.caption_anchors

    def flaky(page):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("page exploded")
        return real(page)

    monkeypatch.setattr(scan_mod, "caption_anchors", flaky)
    manifest = PdfStructureScanner().scan(NATURE)

    codes = [i.code for i in manifest.issues]
    assert "SCAN_PAGE_FAILED" in codes
    issue = next(i for i in manifest.issues if i.code == "SCAN_PAGE_FAILED")
    assert issue.severity is IssueSeverity.WARNING
    assert issue.stage is PipelineStage.SCAN
    assert issue.retryable is True


def test_page_level_failure_does_not_lose_the_whole_document(monkeypatch):
    import qyunslation.structure.scan_pdf as scan_mod

    calls = {"n": 0}
    real = scan_mod.caption_anchors

    def flaky(page):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("page exploded")
        return real(page)

    monkeypatch.setattr(scan_mod, "caption_anchors", flaky)
    manifest = PdfStructureScanner().scan(NATURE)

    assert manifest.summary.figure_count >= 5
    assert manifest.objects
