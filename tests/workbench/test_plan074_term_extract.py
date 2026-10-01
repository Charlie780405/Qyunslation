# SPDX-License-Identifier: MPL-2.0
from qyunslation.workbench.term_extract import discover_term_occurrences


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
