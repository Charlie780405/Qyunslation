# SPDX-License-Identifier: MPL-2.0
"""PLAN-080e：职务保留与原因枚举。正例要保留，标题和句子不能被误保留。"""
from __future__ import annotations

import pytest

from qyunslation.structure import babeldoc_policy as bp
from qyunslation.structure import entity_preserve as ep

TITLES = [
    "General Manager",
    "Chief Medical Officer",
    "Regulatory Lead, Acme CRO",
    "Senior Director, Regulatory Affairs",
    "Vice President of Clinical Development",
    "Head of Biostatistics",
    "Clinical Reviewer, DO/OSM",
    "Statistical Team Leader, OB/DBIV",
    "Senior Project Manager, OND/OTBB/SRS",
    "Assistant to the General Manager",
    "R&D Director",
    "Co-founder",
]

MUST_TRANSLATE = [
    "Background",
    "Clinical Pharmacology",
    "Statistical Issues",
    "Project Manager Responsibilities",
    "Statistical Analysis Plan",
    "Review Lead Assessment",
    "The Director will review the application.",
    "Please contact the Regulatory Lead for questions about the submission.",
    "Contact the Regulatory Lead.",
    "Director of the Study Operations Group reviews all safety reports",
]


@pytest.mark.parametrize("text", TITLES)
def test_job_titles_are_preserved_with_a_reason(text):
    assert ep.is_job_title(text)
    assert ep.preserve_reason(text) == ep.JOB_TITLE
    bp.reset_preserve_gate()
    assert bp.paragraph_is_preserved(text) is True


@pytest.mark.parametrize("text", MUST_TRANSLATE)
def test_headings_and_sentences_are_not_mistaken_for_titles(text):
    assert not ep.is_job_title(text)
    assert ep.preserve_reason(text) is None
    bp.reset_preserve_gate()
    assert bp.paragraph_is_preserved(text) is False


def test_reason_enumeration():
    assert ep.preserve_reason("Alex Morgan, MD") == ep.PERSON_NAME
    assert ep.preserve_reason("Example Biopharma Co., Ltd.") == ep.ORG_NAME
    # 带机构标记的职务按职务记，而不是机构
    assert ep.preserve_reason("Deputy Director, Office of New Drugs (OND)") == ep.JOB_TITLE
    assert ep.preserve_reason("Hello there") is None
    assert set(ep.REASONS) == {ep.PERSON_NAME, ep.JOB_TITLE, ep.ORG_NAME}


def test_filter_for_llm_matches_the_paragraph_policy():
    bp.reset_preserve_gate()
    kept = bp.filter_paragraphs_for_llm(["Medical Director", "Background", "Clinical Reviewer, DO/OSM"])
    assert kept == ["Background"]


def test_job_title_is_not_used_as_llm_context():
    assert bp.title_is_usable_context("Medical Director") is False
    assert bp.title_is_usable_context("Background") is True


def test_empty_and_overlong_input_are_not_titles():
    assert ep.preserve_reason("") is None
    assert ep.preserve_reason(None) is None
    assert not ep.is_job_title("Senior Medical Director " * 8)
