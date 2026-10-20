# SPDX-License-Identifier: MPL-2.0
"""PLAN-082 S5: TABLE_TEXT_OVERLAP QA and table postprocess mode."""
from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.pipeline.qa.pdf_inspect import check_table_text_overlap
from qyunslation.pipeline.stages.postprocess import table_postprocess_mode


def test_table_postprocess_mode_defaults_to_literature(monkeypatch):
    monkeypatch.delenv("QYUNSLATION_TABLE_POSTPROCESS", raising=False)
    assert table_postprocess_mode() == "literature"
    monkeypatch.setenv("QYUNSLATION_TABLE_POSTPROCESS", "off")
    assert table_postprocess_mode() == "off"
    monkeypatch.setenv("QYUNSLATION_TABLE_POSTPROCESS", "translate")
    assert table_postprocess_mode() == "translate"


def test_sample_mono_tables_trigger_overlap_blocker():
    sample = Path(
        "var/translation-runs/d8faef9f-5f8a-41a1-a65b-e9a4fc551e06/"
        "80d8796e-54aa-45bf-9a2f-80bfe26401c1/generation-1/output/"
        "09-LIT-2026-CM512-Trial.no_watermark.zh.mono.pdf"
    )
    source = Path(
        "var/pipeline/runs/80d8796e-54aa-45bf-9a2f-80bfe26401c1/gen-1/input/"
        "09-LIT-2026-CM512-Trial.pdf"
    )
    if not sample.is_file() or not source.is_file():
        pytest.skip("CM512 sample not present")
    findings = check_table_text_overlap(sample, source_path=source, min_pairs=20)
    assert findings and findings[0].code == "TABLE_TEXT_OVERLAP"
    assert findings[0].severity == "blocker"
    pages = set(findings[0].evidence["pages"])
    assert pages & {5, 6}


def test_clean_single_page_pdf_has_no_overlap(tmp_path):
    import pymupdf as fitz

    path = tmp_path / "clean.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello table clean", fontsize=12)
    doc.save(path)
    doc.close()
    assert check_table_text_overlap(path, min_pairs=1) == []
