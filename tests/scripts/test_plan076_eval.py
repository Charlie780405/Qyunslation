from __future__ import annotations

from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa
from qyunslation.pipeline.ad_termbase import build_ad_term_policy


def test_eval_primitives_are_source_conditioned_and_bidirectional():
    en_source = "Patients with atopic dermatitis received dupilumab 300 mg."
    en_target = "特应性皮炎患者接受了度普利尤单抗 300 mg。"
    en_policy = build_ad_term_policy(en_source, "en-zh")
    assert not run_ad_deterministic_qa(
        QaContext(en_source, en_target, "en-zh", en_policy["terms"])
    )

    zh_source = "特应性皮炎患者接受了度普利尤单抗 300 mg。"
    zh_target = "Patients with atopic dermatitis received dupilumab 300 mg."
    zh_policy = build_ad_term_policy(zh_source, "zh-en")
    assert not run_ad_deterministic_qa(
        QaContext(zh_source, zh_target, "zh-en", zh_policy["terms"])
    )
