# SPDX-License-Identifier: MPL-2.0
import pytest

from qyunslation.pipeline.model_profiles import validate_selection


def test_internal_rejects_external_translator():
    with pytest.raises(ValueError):
        validate_selection(
            classification="internal",
            model_profile_id="public-deepseek-flash",
        )


def test_confidential_rejects_term_external():
    with pytest.raises(ValueError):
        validate_selection(
            classification="confidential",
            model_profile_id="internal-qwen-quality",
            term_profile_id="term-deepseek-flash",
        )


def test_public_allows_qwen_default():
    c, model, term = validate_selection(
        classification="public",
        model_profile_id=None,
    )
    assert c == "public"
    assert model == "internal-qwen-quality"
    assert term is None
