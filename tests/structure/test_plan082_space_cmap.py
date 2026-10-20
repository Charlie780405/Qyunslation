# SPDX-License-Identifier: MPL-2.0
"""PLAN-082 S4: ToUnicode space-glyph repair."""
from __future__ import annotations

from pathlib import Path

from qyunslation.structure.pdf_space_cmap import _inject_space_mapping, fix_space_cmap_pdf


def test_injects_cid3_to_space_into_bfchar_block():
    stream = b"""/CIDInit /ProcSet findresource begin
begincmap
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
2 beginbfchar
<0006><0023>
<0008><0025>
endbfchar
endcmap
"""
    updated, changed = _inject_space_mapping(stream)
    assert changed is True
    text = updated.decode("latin-1")
    assert "3 beginbfchar" in text
    assert "<0003><0020>" in text
    assert text.index("<0003><0020>") < text.index("<0006><0023>")


def test_skips_when_cid3_already_mapped():
    stream = b"1 beginbfchar\n<0003><0020>\nendbfchar\n"
    updated, changed = _inject_space_mapping(stream)
    assert changed is False
    assert updated == stream


def test_fix_space_cmap_on_sample_removes_u0003_from_default_extraction(tmp_path, monkeypatch):
    sample = Path(
        "var/translation-runs/d8faef9f-5f8a-41a1-a65b-e9a4fc551e06/"
        "80d8796e-54aa-45bf-9a2f-80bfe26401c1/generation-1/output/"
        "09-LIT-2026-CM512-Trial.no_watermark.zh.mono.pdf"
    )
    if not sample.is_file():
        return
    import pymupdf as fitz

    monkeypatch.setenv("QYUNSLATION_FIX_SPACE_CMAP", "1")
    copy = tmp_path / sample.name
    copy.write_bytes(sample.read_bytes())
    before = sum(page.get_text("text").count("\x03") for page in fitz.open(copy))
    assert before > 0
    summary = fix_space_cmap_pdf(copy)
    assert summary["streams_patched"] >= 1
    after = sum(page.get_text("text").count("\x03") for page in fitz.open(copy))
    assert after == 0
