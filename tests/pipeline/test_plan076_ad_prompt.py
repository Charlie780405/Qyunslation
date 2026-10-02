from __future__ import annotations

import pytest

from qyunslation.pipeline.ad_prompt import (
    AD_DOMAIN_PROFILE,
    PromptContext,
    compile_prompt,
    detect_domain_evidence,
)


def test_ad_prompt_is_direction_and_document_specific():
    context = PromptContext(
        domain_profile="ad",
        direction="en-zh",
        document_profile="医学研究文献",
        task="translate",
    )
    compiled = compile_prompt(context)

    assert compiled.profile_id == "ad.en-zh.literature.translate.v1"
    assert compiled.version == "076-v1"
    assert compiled.digest.startswith("sha256:")
    assert "特应性皮炎" in compiled.text
    assert "English → 简体中文" in compiled.text
    assert "不要把药物、靶点、剂量、统计量或终点改写成事实" in compiled.text


def test_prompt_digest_is_deterministic_and_raw_prompt_is_not_required_for_snapshot():
    context = PromptContext("ad", "zh-en", "临床研究文档", "translate")
    first = compile_prompt(context)
    second = compile_prompt(context)

    assert first.digest == second.digest
    assert first.snapshot()["profile_id"] == "ad.zh-en.clinical.translate.v1"
    assert first.snapshot()["digest"] == first.digest
    assert "text" not in first.snapshot()


def test_ad_profile_rejects_unsupported_direction_or_document():
    with pytest.raises(ValueError, match="unsupported AD direction"):
        compile_prompt(PromptContext("ad", "fr-zh", "医学研究文献", "translate"))
    with pytest.raises(ValueError, match="unsupported AD document profile"):
        compile_prompt(PromptContext("ad", "en-zh", "监管申报材料", "translate"))


def test_domain_evidence_requires_ad_anchor():
    assert detect_domain_evidence("Patients with atopic dermatitis received dupilumab.")
    assert detect_domain_evidence("The weather was sunny and the sample was archived.") is False


def test_general_profile_keeps_backward_compatible_compilation():
    compiled = compile_prompt(PromptContext("general", "en-zh", "通用医药文档", "translate"))
    assert compiled.profile_id == "general.en-zh.general.translate.v1"
    assert compiled.domain_profile == "general"
    assert "特应性皮炎" not in compiled.text
