# SPDX-License-Identifier: MPL-2.0
"""PLAN-080a：送 LLM 前的保留策略不得把正文段落整段留成英文。

两个根因（见 docs/plans/PLAN-080-*）：
1. 编号段落（"2. ..."、"1 ..."）无论是否处于参考文献区都被当作参考文献条目保留；
2. 含 "Co., Ltd." 等机构标记的长正文句被判为署名/机构而保留。
"""
import pytest

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
    "On June 12, 2026, Example Biopharma Co., Ltd. (Example) submitted this BPD Type 2b "
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
    assert classify_frontmatter_text("Example Biopharma Co., Ltd.").role == AFFILIATION
    reset_preserve_gate()
    assert bp.paragraph_is_preserved("Example Biopharma Co., Ltd.") is True


def test_short_prose_sentence_with_company_suffix_is_body():
    """没有动词表里的词、也不到 30 词的正文句，靠功能词线索识别为正文。"""
    text = (
        "On June 12, 2026, Example Biopharma Co., Ltd. submitted this meeting request "
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


CITATIONS = [
    "1. Smith J, Doe A, Lee K. Efficacy of drug X in atopic dermatitis. J Allergy Clin Immunol. 2024;153(2):345-52. "
    "doi:10.1016/j.jaci.2023.10.001",
    "12 Wollenberg A, Barbarot S, Bieber T, et al. Consensus-based European guidelines. J Eur Acad Dermatol 2018;32:657-82.",
    "3. Doe A et al. Long-term safety of tralokinumab. Br J Dermatol 2021;184(3):437-49.",
    "65. Scarisbrick, J. J. & Morris, S. How big is your hand and should you use it to score skin in cutaneous "
    "T-cell lymphoma? Br. J. Dermatol. 184, 437–449 (2021).",
]
NON_STANDARD_HEADINGS = [
    "7. References",
    "REFERENCES AND NOTES",
    "Literature Cited",
    "Works Cited",
    "Reference List",
    "VII. REFERENCES",
    "引用文献",
]


@pytest.mark.parametrize("heading", NON_STANDARD_HEADINGS)
def test_non_standard_reference_headings_are_recognised(heading):
    from qyunslation.structure.references import is_reference_heading

    assert is_reference_heading(heading)
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(heading) is True
    assert bp.paragraph_is_preserved(CITATIONS[0]) is True


@pytest.mark.parametrize("citation", CITATIONS)
def test_journal_citations_are_kept_even_without_any_heading(citation):
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(citation) is True
    assert filter_paragraphs_for_llm([citation]) == []


@pytest.mark.parametrize(
    "text",
    [
        STATS_ITEM,
        FOOTNOTE,
        "3. In 2019, the sponsor submitted the protocol and agreed to the analysis plan after the meeting.",
        "1 Guidance for Industry and FDA Staff, Applying Human Factors (February 2016) is available online.",
        "4. Smith, J. said in 2020 that the plan was acceptable and would be reviewed again after the meeting.",
    ],
)
def test_numbered_regulatory_text_with_a_year_is_still_translated(text):
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(text) is False


def test_headings_that_are_really_sentences_do_not_start_the_references_gate():
    from qyunslation.structure.references import is_reference_heading

    for text in ("See References for details", "The references were reviewed.", "7 References were checked"):
        assert not is_reference_heading(text)


MERGED_REFERENCES = (
    "activity in patients with atopic dermatitis. J. Dermatol. Sci. 44, 93–99 (2006). 47. Bissonnette, R. et al. "
    "Clinical and molecular effects of oral CCR4 antagonist RPT193 in atopic dermatitis: a phase 1 study. "
    "Allergy 79, 924–936 (2024). 48. Karlen, H. et al. IL-15 expression patterns in atopic dermatitis. "
    "Int. Arch. Allergy Immunol. 181, 417–421 (2020)."
)


def test_merged_reference_paragraph_is_kept_regardless_of_order_and_heading():
    """双栏文献里 BabelDOC 的段落顺序不是阅读顺序，合并成一个从条目中间开头的长段落时，状态机会漏掉它。"""
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(MERGED_REFERENCES) is True
    assert filter_paragraphs_for_llm([MERGED_REFERENCES]) == []


@pytest.mark.parametrize(
    "text",
    [
        "Previous studies reported consistent effects (Smith et al., 2020; Jones and Lee, 2021) in this population.",
        "The trial was registered (doi: 10.1000/xyz) and results were published in 2023 after the review.",
        "Treatment with 300 mg every 2 weeks (2024) was well tolerated, as reported earlier. Patients, n = 45.",
        "See Allergy 79, 924–936 (2024) for the original description of the assay.",
    ],
)
def test_body_text_with_at_most_one_citation_shape_is_translated(text):
    reset_preserve_gate()
    assert bp.paragraph_is_preserved(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "2. 试验方案摘要未详述主要疗效终点计划的亚组分析。",
        "1 我们定期更新指导原则。",
        "总经理",
        "法规事务总监",
        "申请人联系人：周清红",
        "三生国健药业（上海）股份有限公司",
        "一、题目和背景",
    ],
)
def test_chinese_source_text_is_never_kept_by_the_english_rules(text):
    """中译英：这些规则只针对英文写法，中文原文（含职务、公司名）照常翻译。"""
    from qyunslation.structure.entity_preserve import is_job_title, preserve_reason

    reset_preserve_gate()
    assert bp.paragraph_is_preserved(text) is False
    assert is_job_title(text) is False
    assert preserve_reason(text) is None
