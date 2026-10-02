from __future__ import annotations

from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa


def test_ad_qa_checks_bidirectional_drug_term_and_dose():
    findings = run_ad_deterministic_qa(
        QaContext(
            source="Patients received dupilumab 300 mg every 2 weeks.",
            target="患者接受了度普利尤单抗 300 mg，每 2 周一次。",
            direction="en-zh",
            terms={"dupilumab": "度普利尤单抗"},
        )
    )
    assert findings == []

    findings = run_ad_deterministic_qa(
        QaContext(
            source="Patients received dupilumab 300 mg every 2 weeks.",
            target="患者接受了某药物 30 mg，每 2 周一次。",
            direction="en-zh",
            terms={"dupilumab": "度普利尤单抗"},
        )
    )
    assert {item.code for item in findings} >= {"AD_TERM_MISSING", "AD_NUMBER_DRIFT"}


def test_ad_qa_checks_negation_and_modality_in_both_directions():
    findings = run_ad_deterministic_qa(
        QaContext(
            source="No serious adverse events were observed.",
            target="观察到严重不良事件。",
            direction="en-zh",
        )
    )
    assert any(item.code == "AD_NEGATION_DRIFT" for item in findings)

    findings = run_ad_deterministic_qa(
        QaContext(
            source="不得用于妊娠患者。",
            target="It may be used in pregnant patients.",
            direction="zh-en",
        )
    )
    assert any(item.code == "AD_MODALITY_DRIFT" for item in findings)


def test_ad_qa_ignores_publication_years_as_protected_dose_numbers():
    findings = run_ad_deterministic_qa(
        QaContext(
            source="The study was conducted in 2024.",
            target="本研究于 2025 年开展。",
            direction="en-zh",
        )
    )
    assert not any(item.code == "AD_NUMBER_DRIFT" for item in findings)
