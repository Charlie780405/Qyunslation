# SPDX-License-Identifier: MPL-2.0
import pytest

from qyunslation.workbench.term_extract import (
    TermExtractionDegraded,
    discover_structured_medical_terms,
    discover_term_occurrences,
)


def test_balanced_medical_extraction_finds_poster_gold_terms_and_excludes_metadata():
    source = """Dupilumab for a patient with vitiligo and severe atopic dermatitis
Patricia Curtin BS, Jessica Gai BA, MS, Michael Dans MD
1 Department of Dermatology, New York Medical College, Valhalla, NY 10595
Dupilumab is a monoclonal antibody that inhibits IL-4 and IL-13 signaling.
The melanocyte response improved. The patient used SPF 30+ and was not in the ICU.
References
Curtin P. Vitiligo case report. 2024;10:1-2.
"""

    rows = discover_term_occurrences(source, "度普利尤单抗；vitiligo；IL-4；IL-13；melanocyte")
    terms = {row["source_term"] for row in rows}

    assert {"Dupilumab", "vitiligo", "atopic dermatitis", "IL-4", "IL-13", "melanocyte"} <= terms
    assert "Patricia Curtin" not in terms
    assert "New York Medical College" not in terms
    assert "ICU" not in terms
    assert "SPF" not in terms
    assert all("Curtin P." not in occurrence["source_context"] for row in rows for occurrence in row["occurrences"])


def test_occurrences_are_deduplicated_by_normalized_form_without_silent_cap():
    source = "Vitiligo improved. vitiligo recurred. " + " ".join(
        f"IL-{number}" for number in range(1, 51)
    )

    rows = discover_term_occurrences(source, "白癜风改善；vitiligo")
    by_norm = {row["source_norm"]: row for row in rows}

    assert len(by_norm["vitiligo"]["occurrences"]) == 2
    assert len([key for key in by_norm if key.startswith("il-")]) == 50
    assert by_norm["vitiligo"]["observed_target"] == "vitiligo"
    assert by_norm["il-1"]["observed_target"] == ""


class _StructuredProvider:
    def translate(self, source, *, system=None):
        assert "Janus kinase" in source
        assert "逐字存在" in system
        return """[
          {"source_term":"Janus kinase-signal transducer and activator of transcription pathway",
           "term_type":"pathway", "recommended_target":"JAK-STAT通路", "reason":"机制通路"},
          {"source_term":"hallucinated disease", "term_type":"disease", "reason":"不存在"}
        ]"""


def test_structured_model_supplements_only_verbatim_source_terms():
    source = (
        "The Janus kinase-signal transducer and activator of transcription pathway "
        "was evaluated in the study."
    )
    rows = discover_structured_medical_terms(source, "评估了JAK-STAT通路。", _StructuredProvider())

    assert [row["source_term"] for row in rows] == [
        "Janus kinase-signal transducer and activator of transcription pathway"
    ]
    assert rows[0]["suggested_target"] == "JAK-STAT通路"
    assert rows[0]["observed_target"] == ""
    assert rows[0]["extraction_metadata"]["reason"] == "structured_model:机制通路"


def test_structured_model_failure_is_explicitly_degraded():
    class Broken:
        def translate(self, source, *, system=None):
            raise RuntimeError("offline")

    with pytest.raises(TermExtractionDegraded):
        discover_structured_medical_terms("atopic dermatitis", "特应性皮炎", Broken())
