"""PLAN-033d：参考文献标题可译、条目不译、术语不收录条目。"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.models import ObjectType
from qyunslation.structure.references import (
    is_reference_entry,
    is_reference_heading,
    text_excluding_reference_entries,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import proper_nouns as pn  # noqa: E402


def test_heading_and_intext_citation_are_distinct():
    assert is_reference_heading("References")
    assert is_reference_heading("参考文献")
    assert not is_reference_heading("as shown in References above")
    assert is_reference_entry("[12] Smith J. Dupilumab trial. 2024.")
    assert is_reference_entry("1. Author SM, et al. Trial. 2024.")
    assert is_reference_entry("1 Author SM, et al. Trial. 2024.")
    assert is_reference_entry("1Langanan SM, Irvine AD, Weidinger S.")
    assert not is_reference_entry(
        "Patients were enrolled, see [12] for details. MedImmune staff attended."
    )
    assert not is_reference_entry("2024 was a pivotal year for biologics.")


def test_synthetic_references_scope(generated_structure_fixtures: Path):
    path = generated_structure_fixtures / "references-section.pdf"
    manifest = PdfStructureScanner().scan(path)
    bodies = [o for o in manifest.objects if o.type is ObjectType.BODY]
    texts = {
        (o.translatable_blocks[0].source_text if o.translatable_blocks else ""): o
        for o in bodies
    }
    cite = next(o for t, o in texts.items() if "see [12]" in t)
    assert cite.planned_action == "babeldoc_text_layer"
    assert cite.semantic_scope == "body"
    entries = [o for o in bodies if o.reason_code == "reference_entry"]
    assert len(entries) == 2
    assert all(o.planned_action == "preserve" for o in entries)
    assert all(o.semantic_scope == "references" for o in entries)


def test_harvest_skips_reference_entries(generated_structure_fixtures: Path):
    path = generated_structure_fixtures / "references-section.pdf"
    doc = pymupdf.open(path)
    try:
        blob = text_excluding_reference_entries(doc)
    finally:
        doc.close()
    assert "see [12]" in blob
    assert "MedImmune" in blob
    assert "IQVIA" not in blob
    assert "GenScend" not in blob
    terms = pn.harvest_from_text(blob)
    assert "MedImmune" in terms
    assert "IQVIA" not in terms
    assert "GenScend" not in terms
