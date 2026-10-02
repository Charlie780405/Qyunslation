from __future__ import annotations

from qyunslation.pipeline.ad_termbase import build_ad_term_policy, load_ad_terms


def test_ad_termbase_supports_both_directions_and_longest_match():
    en_zh = build_ad_term_policy("Patients with atopic dermatitis received dupilumab.", "en-zh")
    assert en_zh["direction"] == "en-zh"
    assert en_zh["terms"]["atopic dermatitis"] == "特应性皮炎"
    assert en_zh["terms"]["dupilumab"] == "度普利尤单抗"
    assert en_zh["termbase_version"].startswith("076-ad-")

    zh_en = build_ad_term_policy("特应性皮炎患者接受了度普利尤单抗。", "zh-en")
    assert zh_en["terms"]["特应性皮炎"] == "atopic dermatitis"
    assert zh_en["terms"]["度普利尤单抗"] == "dupilumab"


def test_ad_termbase_marks_identity_targets_and_high_risk_drugs():
    rows = load_ad_terms()
    il4 = next(row for row in rows if row["source"] == "IL-4Rα")
    dup = next(row for row in rows if row["source"] == "dupilumab")
    assert il4["do_not_translate"] is True
    assert dup["risk"] == "high"
