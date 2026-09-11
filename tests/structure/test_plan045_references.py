# SPDX-License-Identifier: MPL-2.0
"""PLAN-045b：粘连序号参考文献条目与 LLM 过滤。"""
from __future__ import annotations

from qyunslation.structure.babeldoc_policy import (
    filter_paragraphs_for_llm,
    reset_preserve_gate,
)
from qyunslation.structure.references import is_reference_entry


def test_glued_and_spaced_entries():
    assert is_reference_entry("1Langanan SM, Irvine AD, Weidinger S. Atopic dermatitis.")
    assert is_reference_entry("1. Author SM, et al. Trial. 2024.")
    assert is_reference_entry("[1] Author SM, et al. Trial. 2024.")
    assert is_reference_entry("12 Wollenberg A, et al. Guideline.")


def test_filter_skips_glued_entries_after_heading():
    reset_preserve_gate()
    kept = filter_paragraphs_for_llm(
        [
            "Abstract body text about tralokinumab.",
            "References",
            "1Langanan SM, Irvine AD. Lancet 2020.",
            "2. Wollenberg A, et al. JEADV 2020.",
            "see [12] for details remains body only before refs",
        ]
    )
    assert kept == ["Abstract body text about tralokinumab."]


def test_intext_citation_still_translatable_before_refs():
    reset_preserve_gate()
    kept = filter_paragraphs_for_llm(
        [
            "Patients were enrolled, see [12] for details.",
            "References",
            "1Langanan SM. Title.",
        ]
    )
    assert kept == ["Patients were enrolled, see [12] for details."]
