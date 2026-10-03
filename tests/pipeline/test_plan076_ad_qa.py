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


def _codes(source: str, target: str, direction: str, **kwargs) -> set[str]:
    return {item.code for item in run_ad_deterministic_qa(QaContext(source, target, direction, **kwargs))}


def test_ad_qa_number_check_is_order_free_and_format_tolerant():
    source = (
        "Asthma affects over 300 million individuals; prevalence was 20–50% (searched 19 January 2026). "
        "Milk allergy was most common (n = 52, 26%), followed by egg (n = 48, 24%); 200/1850 were screened. "
        "IL-4 and type 2 inflammation [ 6 , 7 ] were assessed with R version 4.3.1 (Tel.: +90-224-295-04-18)."
    )
    target = (
        "哮喘影响超过3亿人；患病率为20%–50%（检索至2026年1月19日）。"
        "最常见为牛奶过敏（n = 52，26%），其次为鸡蛋（n = 48，24%）；共筛查200/1850例。"
        "采用R软件（版本4.3.1）评估了IL-4与2型炎症[6,7]（电话：+90-224-295-04-18）。"
    )
    assert "AD_NUMBER_DRIFT" not in _codes(source, target, "en-zh")


def test_ad_qa_number_check_still_catches_dose_and_statistic_changes():
    assert "AD_NUMBER_DRIFT" in _codes("Dupilumab 300 mg was given.", "给予度普利尤单抗 30 mg。", "en-zh")
    assert "AD_NUMBER_DRIFT" in _codes("The response rate was 62.89%.", "有效率为 68.29%。", "en-zh")
    assert "AD_NUMBER_DRIFT" in _codes("本研究纳入106例患者（P<0.05）。", "A total of 160 patients were included (P<0.05).", "zh-en")
    assert "AD_NUMBER_DRIFT" in _codes("约1780万人受累。", "About 17.8 billion people are affected.", "zh-en")


def test_ad_qa_bare_small_integers_and_durations_are_not_protected():
    assert "AD_NUMBER_DRIFT" not in _codes(
        "Table 2 shows EASI-75 at week 16 in 71 children aged 6–7 years.",
        "表2显示71名6至7岁儿童第16周时的EASI-75。",
        "en-zh",
    )


def test_ad_qa_modality_is_presence_based_and_deontic_only():
    assert "AD_MODALITY_DRIFT" not in _codes(
        "Informed consent cannot be obtained in some cases, and patients may continue therapy.",
        "部分情况下无法获得知情同意，患者可以继续治疗。",
        "en-zh",
    )
    assert "AD_MODALITY_DRIFT" in _codes("该药禁止用于孕妇。", "The drug can be used in pregnant women.", "zh-en")


def test_ad_qa_accepts_curated_term_aliases():
    source = "Patients experienced a flare after stopping topical corticosteroids."
    target = "停用局部糖皮质激素后患者出现发作。"
    terms = {"flare": "急性加重", "topical corticosteroid": "外用糖皮质激素"}
    assert "AD_TERM_MISSING" in _codes(source, target, "en-zh", terms=terms)
    aliases = {"flare": ("发作", "加重"), "topical corticosteroid": ("局部糖皮质激素",)}
    assert "AD_TERM_MISSING" not in _codes(source, target, "en-zh", terms=terms, aliases=aliases)


def test_ad_qa_ignores_publication_years_as_protected_dose_numbers():
    findings = run_ad_deterministic_qa(
        QaContext(
            source="The study was conducted in 2024.",
            target="本研究于 2025 年开展。",
            direction="en-zh",
        )
    )
    assert not any(item.code == "AD_NUMBER_DRIFT" for item in findings)
