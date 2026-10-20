# SPDX-License-Identifier: MPL-2.0
"""PLAN-080a：送 LLM 前的保留策略不得把正文段落整段留成英文。

两个根因（见 docs/plans/PLAN-080-*）：
1. 编号段落（"2. ..."、"1 ..."）无论是否处于参考文献区都被当作参考文献条目保留；
2. 含 "Co., Ltd." 等机构标记的长正文句被判为署名/机构而保留。
"""
from qyunslation.structure import babeldoc_policy as bp
from qyunslation.structure.frontmatter import AFFILIATION, BODY, classify_frontmatter_text
from qyunslation.structure.babeldoc_policy import filter_paragraphs_for_llm, reset_preserve_gate

STATS_ITEM = (
    "2. The protocol synopsis does not detail planned subgroup analyses for the primary "
    "efficacy endpoint. Evaluating the consistency of the treatment effect across different "
    "subpopulations is a standard expectation."
)
FOOTNOTE = "1 We update guidances periodically. For the most recent version of a guidance."
BACKGROUND = (
    "On June 12, 2026, Jiangsu GenScend Biopharma Co., Ltd. (Jiangsu) submitted this BPD Type 2b "
    "meeting request to discuss the proposed regulatory strategy, the comparative analytical "
    "assessment strategy, and the non-clinical and clinical development plan."
)


def test_numbered_body_item_is_not_preserved_outside_references():
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(STATS_ITEM) is False
    assert bp.paragraph_is_preserved(FOOTNOTE) is False


def test_numbered_items_are_sent_to_llm_outside_references():
    reset_preserve_gate()
    kept = filter_paragraphs_for_llm(["Background text about the study.", STATS_ITEM, FOOTNOTE])
    assert kept == ["Background text about the study.", STATS_ITEM, FOOTNOTE]


def test_numbered_entries_are_preserved_after_references_heading():
    reset_preserve_gate()
    assert bp.paragraph_is_preserved("References") is True
    assert bp.paragraph_is_preserved("2. Wollenberg A, et al. JEADV 2020.") is True
    assert bp.paragraph_is_preserved("1Langanan SM, Irvine AD. Lancet 2020.") is True


def test_bracket_entry_is_preserved_without_heading():
    reset_preserve_gate()
    assert bp.paragraph_is_preserved("[12] Smith J. Title. J Allergy. 2024;1:1-8.") is True


def test_intext_citation_stays_translatable():
    reset_preserve_gate()
    assert bp.paragraph_is_preserved("Patients were enrolled, see [12] for details.") is False


def test_appendix_ends_reference_preservation():
    reset_preserve_gate()
    assert bp.paragraph_is_preserved("References") is True
    assert bp.paragraph_is_preserved("Appendix extra analyses") is False
    assert bp.paragraph_is_preserved(STATS_ITEM) is False


def test_long_sentence_with_company_suffix_is_body():
    result = classify_frontmatter_text(BACKGROUND)
    assert result.role == BODY
    assert result.preserve is False
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(BACKGROUND) is False


def test_long_body_sentence_with_email_is_not_an_author_line():
    text = (
        "Refer to guidance for industry on electronic submissions, and contact the Agency at "
        "ceder@fda.hhs.gov before the submission is sent through the gateway."
    )
    assert classify_frontmatter_text(text).role == BODY
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(text) is False


def test_short_affiliation_line_is_still_preserved():
    assert classify_frontmatter_text("Jiangsu GenScend Biopharma Co., Ltd.").role == AFFILIATION
    reset_preserve_gate()
    assert bp.paragraph_is_preserved("Jiangsu GenScend Biopharma Co., Ltd.") is True


def test_short_prose_sentence_with_company_suffix_is_body():
    """没有动词表里的词、也不到 30 词的正文句，靠功能词线索识别为正文。"""
    text = (
        "On June 12, 2026, Jiangsu GenScend Biopharma Co., Ltd. submitted this meeting request "
        "to discuss the proposed strategy and plan."
    )
    assert classify_frontmatter_text(text).role == BODY
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(text) is False


def test_short_institution_lines_with_one_function_word_stay_affiliations():
    for text in (
        "Office of the Director, Center for Drug Evaluation and Research",
        "Division of Pharmacology and Toxicology for Rare Diseases",
        "Department of Medicine, University of California, San Francisco",
    ):
        assert classify_frontmatter_text(text).role == AFFILIATION, text
