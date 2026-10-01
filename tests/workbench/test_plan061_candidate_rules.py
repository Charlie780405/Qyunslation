# SPDX-License-Identifier: MPL-2.0
"""PLAN-061：候选准入规则排除噪声、保留专业词。"""
from __future__ import annotations

from qyunslation.glossary.candidate_rules import (
    EXCLUDE_CELL_PRESERVE,
    EXCLUDE_DENYLIST,
    EXCLUDE_PATTERN,
    EXCLUDE_TOO_SHORT,
    classify_risk_by_rules,
    rules_version,
    should_exclude_from_termbase,
)
from qyunslation.workbench.evidence import BilingualTermEvidence, classify_risk, extract_term_pairs


def test_rules_version_matches_toml():
    assert rules_version() == "074-v1"


def test_numeric_dose_and_ratio_tokens_are_excluded():
    cases = {
        "300 mg": EXCLUDE_CELL_PRESERVE,
        "300mg": EXCLUDE_CELL_PRESERVE,
        "14/18": EXCLUDE_PATTERN,
        "77.8": EXCLUDE_CELL_PRESERVE,
        "Q2W": EXCLUDE_CELL_PRESERVE,
        "10 mg/kg": EXCLUDE_CELL_PRESERVE,
        "2.5%": EXCLUDE_CELL_PRESERVE,
        "UK": EXCLUDE_TOO_SHORT,
        "OR": EXCLUDE_DENYLIST,
        "TARGET": EXCLUDE_DENYLIST,
        "ACAD": EXCLUDE_DENYLIST,
        "Inc": EXCLUDE_DENYLIST,
        "RC": EXCLUDE_TOO_SHORT,
        "AD": EXCLUDE_TOO_SHORT,
        "TTT": EXCLUDE_DENYLIST,
        "Page 3": EXCLUDE_PATTERN,  # junk 兜底亦可，但规则文件应先命中 PATTERN
        "NCT03131648": EXCLUDE_PATTERN,
        "ChiCTR2100041234": EXCLUDE_PATTERN,
    }
    for source, reason in cases.items():
        excluded, got = should_exclude_from_termbase(source)
        assert excluded is True, source
        assert got == reason, (source, got)


def test_professional_terms_stay_in_the_queue():
    for source in ("tralokinumab", "dermatitis", "IL-13", "IL-6", "LCZ696", "NHS", "ABC-101"):
        excluded, reason = should_exclude_from_termbase(source)
        assert excluded is False, (source, reason)


def test_institution_abbreviations_are_high_risk():
    assert classify_risk_by_rules("NHS") == "high"
    assert classify_risk_by_rules("ICU") == "high"
    assert classify_risk("dupilumab treatment") == "high"
    assert classify_risk("IL-4Rα antibody") == "high"
    assert classify_risk("SSGJ-611-CRS-III-01") == "high"
    assert classify_risk("Capital Medical University") == "high"


def test_synthetic_extraction_drops_dose_and_keeps_drug():
    rows = extract_term_pairs(
        [
            BilingualTermEvidence(
                source_text="tralokinumab 300 mg Q2W versus placebo (14/18).",
                target_text="tralokinumab 300 mg Q2W 对比安慰剂（14/18）。",
            )
        ]
    )
    sources = {row["source_term"] for row in rows}
    assert "tralokinumab" in sources
    assert not {"300 mg", "Q2W", "14/18"} & sources


def test_registry_ids_are_not_extracted():
    rows = extract_term_pairs(
        [
            BilingualTermEvidence(
                source_text="Registered as NCT03131648 and ChiCTR2100041234.",
                target_text="登记号 NCT03131648 与 ChiCTR2100041234。",
            )
        ]
    )
    sources = {row["source_term"] for row in rows}
    assert "NCT03131648" not in sources
    assert "ChiCTR2100041234" not in sources
