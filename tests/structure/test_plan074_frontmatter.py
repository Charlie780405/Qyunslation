# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from qyunslation.structure.frontmatter import (
    AFFILIATION,
    AUTHOR,
    BODY,
    classify_frontmatter_text,
)
from qyunslation.structure.babeldoc_policy import (
    filter_paragraphs_for_llm,
    paragraph_is_preserved,
    title_is_usable_context,
)
from qyunslation.structure.models import BlockRole, TranslatableBlock


def test_multi_author_line_is_preserved_metadata():
    text = "Patricia Curtin BS 1, Jessica Gai, BA, MS1, Michael Vittori M.D., PharmD2"
    result = classify_frontmatter_text(text)
    assert result.role == AUTHOR
    assert result.preserve is True
    assert result.review_required is False


def test_corresponding_author_email_and_orcid_are_preserved():
    for text in (
        "Corresponding author: Jane Smith, MD, PhD; jane.smith@example.org",
        "John Doe, PhD, ORCID 0000-0002-1825-0097",
    ):
        result = classify_frontmatter_text(text)
        assert result.role == AUTHOR
        assert result.preserve is True


def test_affiliation_keeps_its_original_text_without_review():
    for text in (
        "1 School of Medicine, New York Medical College, Valhalla, NY 10595; "
        "2 Department of Dermatology, New York Medical College",
        "Jiangsu GenScend Biopharma Co., Ltd.",
    ):
        result = classify_frontmatter_text(text)
        assert result.role == AFFILIATION
        assert result.preserve is True
        assert result.review_required is False


def test_body_person_mention_is_not_misclassified_as_author():
    for text in (
        "The patient was evaluated by John Smith, MD, after treatment failure.",
        "LABORATORY TEST UNITS FOR CLINICAL TRIALS CDER strongly encourages IND sponsors to identify the units.",
    ):
        result = classify_frontmatter_text(text)
        assert result.role == BODY
        assert result.preserve is False


def test_generic_contact_email_is_not_an_author_line():
    assert classify_frontmatter_text("Email a@b.com").role == BODY


def test_author_and_affiliation_are_excluded_from_translation_and_context():
    author = "Patricia Curtin BS¹, Jessica Gai, BA, MS¹, Michael Dans, MD²"
    affiliation = "1 Department of Dermatology, New York Medical College, Valhalla, NY"

    assert paragraph_is_preserved(author) is True
    assert title_is_usable_context(author) is False
    assert paragraph_is_preserved(affiliation) is True
    assert filter_paragraphs_for_llm([author, affiliation]) == []


def test_english_person_names_with_titles_or_signatures_are_preserved():
    for text in ("Dear Dr. Mei-Fei Yueh:", "Sincerely, William M. Boyd"):
        result = classify_frontmatter_text(text)
        assert result.role == AUTHOR
        assert result.preserve is True


def test_structure_contract_exposes_frontmatter_roles_and_review_flag():
    author = TranslatableBlock(
        block_id="p1:author",
        source_text="Patricia Curtin, BS",
        role=BlockRole.AUTHOR,
        review_required=False,
    )
    affiliation = TranslatableBlock(
        block_id="p1:affiliation",
        source_text="Department of Dermatology, New York Medical College",
        role=BlockRole.AFFILIATION,
        review_required=False,
    )

    assert author.role is BlockRole.AUTHOR
    assert affiliation.review_required is False
