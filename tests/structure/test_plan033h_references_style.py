"""PLAN-033h：参考文献硬保留、LLM spy、字重与段距。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from qyunslation.structure.babeldoc_policy import (
    LlmRequestSpy,
    ReferencePreserveGate,
    filter_paragraphs_for_llm,
    title_is_usable_context,
)
from qyunslation.structure.font_style import cap_body_gap, infer_font_weight, infer_italic
from qyunslation.structure.models import ObjectType, TranslationPolicy
from qyunslation.structure.scan_pdf import PdfStructureScanner


def test_font_name_patterns_override_missing_flags():
    assert infer_font_weight("Times-Bold") == "bold"
    assert infer_font_weight("SourceSerif-Semibold") == "semibold"
    assert infer_font_weight("Inter-Black") == "black"
    assert infer_font_weight("MinionPro.B") == "bold"
    assert infer_font_weight("Times-Roman") == "regular"
    assert infer_font_weight("Times-Roman", flags_bold=True) == "bold"
    assert infer_italic("Times-BoldItalic") is True
    assert infer_italic("Times-Roman") is False


def test_body_gap_caps_abnormal_whitespace():
    assert cap_body_gap(6.0, 12.0) == 6.0
    assert cap_body_gap(80.0, 12.0) == 12.0 * 1.8


def test_llm_spy_sends_zero_reference_requests():
    spy = LlmRequestSpy()
    kept = filter_paragraphs_for_llm(
        [
            "Patients were enrolled, see [12] for details.",
            "References",
            "[1] IQVIA. Dupilumab trial. 2024. https://doi.org/10.1000/xyz",
            "[2] GenScend data on file.",
            "Appendix Supplementary methods",
            "Additional experiments were performed.",
        ],
        spy=spy,
    )
    assert kept == [
        "Patients were enrolled, see [12] for details.",
        "Appendix Supplementary methods",
        "Additional experiments were performed.",
    ]
    assert spy.reference_request_count == 0
    assert not title_is_usable_context("References")


def test_stateful_gate_preserves_heading_and_cross_page_entries():
    gate = ReferencePreserveGate()
    assert gate.should_preserve("References")
    assert gate.should_preserve("[12] Smith J. Title. J Allergy. 2024;1:1-8.")
    assert not gate.should_preserve("Appendix extra analyses")
    assert not gate.should_preserve("We then repeated the assay.")


def test_manifest_heading_and_entries_are_preserve(generated_structure_fixtures):
    path = generated_structure_fixtures / "references-section.pdf"
    manifest = PdfStructureScanner().scan(path)
    bodies = [o for o in manifest.objects if o.type is ObjectType.BODY]
    heading = next(o for o in bodies if o.detector_evidence[0].label == "heading")
    entries = [o for o in bodies if o.reason_code == "reference_entry"]
    cite = next(o for o in bodies if o.semantic_scope == "body")
    assert heading.planned_action == "preserve"
    assert heading.translatable_blocks[0].translation_policy is TranslationPolicy.PRESERVE
    assert all(o.planned_action == "preserve" for o in entries)
    assert all(
        o.translatable_blocks[0].translation_policy is TranslationPolicy.PRESERVE
        for o in entries
    )
    assert cite.planned_action == "babeldoc_text_layer"


def _load_fidelity_patcher():
    path = Path(__file__).resolve().parents[2] / "scripts/apply-pdf2zh-fidelity-033h.py"
    spec = importlib.util.spec_from_file_location("apply_pdf2zh_fidelity_033h", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_il_patcher_hooks_should_translate_even_after_helper_exists():
    patcher = _load_fidelity_patcher()
    source = '''
logger = logging.getLogger(__name__)

    def translate(self, docs: Document) -> None:
        pass

    def _should_translate_paragraph(self, paragraph, translated_ids=None, require_body_text=False):
        if require_body_text and not self._is_body_text_paragraph(paragraph):
            return False
        return True
'''
    patched, changed = patcher.patch_il(source)
    assert changed is True
    assert patched.count("_QY_033H_PRESERVE(paragraph.unicode)") == 1
    assert "reset_preserve_gate" in patched
    again, second = patcher.patch_il(patched)
    assert second is False
    assert again.count("_QY_033H_PRESERVE(paragraph.unicode)") == 1


def test_terms_patcher_skips_preserved_paragraphs_with_pbar():
    patcher = _load_fidelity_patcher()
    source = """
        for paragraph in page.pdf_paragraph:
            if paragraph.debug_id is None or paragraph.unicode is None:
                pbar.advance(1)
                continue
            if is_cid_paragraph(paragraph):
                pbar.advance(1)
                continue
"""
    patched, changed = patcher.patch_terms(source)
    assert changed is True
    assert "paragraph_is_preserved(paragraph.unicode)" in patched
    assert "_QY_033H_PRESERVE" in patched
    assert "pbar.advance(1)" in patched
    again, second = patcher.patch_terms(patched)
    assert second is False
    assert again == patched
