"""PLAN-036a：table_cell_policy 跨路径 parity。"""
from __future__ import annotations

import pytest

from qyunslation.extensions.doc_image_policy import is_numeric_or_unit as image_numeric
from qyunslation.structure.models import TranslationPolicy
from qyunslation.structure.table_cell_policy import (
    classify_cell_policy,
    is_numeric_or_unit,
    is_preserve_cell,
)


@pytest.mark.parametrize(
    ("text", "preserve", "numeric", "policy"),
    [
        ("", True, True, TranslationPolicy.PRESERVE),
        ("42", True, True, TranslationPolicy.PRESERVE),
        ("42.3%", True, True, TranslationPolicy.PRESERVE),
        ("N/A", True, True, TranslationPolicy.PRESERVE),
        ("n=120", True, True, TranslationPolicy.PRESERVE),
        ("100mg", True, True, TranslationPolicy.PRESERVE),
        ("mg", True, True, TranslationPolicy.PRESERVE),
        ("Response 42%", False, False, TranslationPolicy.PROTECT_TOKENS),
        ("Endpoint", False, False, TranslationPolicy.TRANSLATE),
    ],
)
def test_policy_parity_matrix(text, preserve, numeric, policy):
    assert is_preserve_cell(text) is preserve
    assert is_numeric_or_unit(text) is numeric
    assert image_numeric(text) is numeric
    assert classify_cell_policy(text) is policy
