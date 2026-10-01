# SPDX-License-Identifier: MPL-2.0
from qyunslation.pipeline.qa import quality_state_from_findings, run_deterministic_qa, summarize


def test_empty_translation_blocker():
    findings = run_deterministic_qa(translated_text_sample="")
    assert any(f.code == "EMPTY_TRANSLATION" for f in findings)
    assert quality_state_from_findings(findings) == "qa_blocked"


def test_fallback_warning_allows_review():
    findings = run_deterministic_qa(
        translated_text_sample="Fallback to simple translation for paragraph 1"
    )
    assert any(f.code == "FALLBACK_PRESENT" for f in findings)
    assert quality_state_from_findings(findings) == "review_ready"


def test_logo_missing_blocker():
    findings = run_deterministic_qa(logo_present=False, translated_text_sample="ok")
    assert any(f.code == "LOGO_MISSING" for f in findings)


def test_term_high_risk_blocker():
    findings = run_deterministic_qa(
        translated_text_sample="ok",
        term_summary={"high_risk_conflicts": [{"message": "dose drift"}]},
    )
    assert any(f.code == "TERM_HIGH_RISK_CONFLICT" for f in findings)
    assert summarize(findings)["blocker"] >= 1


def test_page_mismatch_blocker():
    findings = run_deterministic_qa(
        translated_text_sample="ok",
        source_page_count=3,
        output_page_count=2,
    )
    assert any(f.code == "PAGE_COUNT_MISMATCH" for f in findings)


def test_generation_mismatch_blocker():
    findings = run_deterministic_qa(
        translated_text_sample="ok",
        settings_snapshot={"generation": 2},
        manifest={"extensions": {"generation": 1}, "objects": [{"id": "a"}]},
    )
    assert any(f.code == "GENERATION_MISMATCH" for f in findings)


def test_none_sample_skips_empty_blocker():
    findings = run_deterministic_qa(translated_text_sample=None)
    assert not any(f.code == "EMPTY_TRANSLATION" for f in findings)
