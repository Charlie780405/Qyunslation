import pytest
from pydantic import ValidationError

from qyunslation.structure import ContentProfile, LayoutMode, ProfileSource
from qyunslation.structure.capabilities import RequirementLevel, all_format_capabilities
from qyunslation.structure.profiles import (
    ProfileDecision,
    ReadingStrategy,
    all_content_profiles,
    profile_for,
    resolve_profile,
)


def test_registry_has_exactly_one_spec_for_each_content_profile():
    specs = all_content_profiles()

    assert {spec.content_profile for spec in specs} == set(ContentProfile)
    assert len(specs) == len(ContentProfile)


def test_profile_specs_do_not_encode_source_formats():
    for spec in all_content_profiles():
        fields = type(spec).model_fields
        assert "source_format" not in fields
        assert "extensions" not in fields


def test_every_core_format_can_pair_with_every_content_profile():
    core_formats = [
        capability.source_format
        for capability in all_format_capabilities()
        if capability.requirement_level is RequirementLevel.CORE
    ]

    combinations = {
        (source_format, profile.content_profile)
        for source_format in core_formats
        for profile in all_content_profiles()
    }

    assert len(combinations) == len(core_formats) * len(ContentProfile)


def test_article_profiles_encode_reading_order_and_figure_table_semantics():
    for name in (
        ContentProfile.RESEARCH_ARTICLE,
        ContentProfile.REVIEW_ARTICLE,
    ):
        spec = profile_for(name)
        assert spec.reading_strategy is ReadingStrategy.READING_ORDER
        assert spec.has_figure_table_semantics is True
        assert {LayoutMode.SINGLE, LayoutMode.DOUBLE, LayoutMode.MULTI}.issubset(
            set(spec.expected_layout_modes)
        )


def test_presentation_and_poster_use_freeform_spatial_priors():
    presentation = profile_for(ContentProfile.PRESENTATION)
    poster = profile_for(ContentProfile.POSTER)

    assert presentation.reading_strategy is ReadingStrategy.SPATIAL
    assert poster.reading_strategy is ReadingStrategy.SPATIAL
    assert LayoutMode.FREEFORM in presentation.expected_layout_modes
    assert LayoutMode.FREEFORM in poster.expected_layout_modes
    assert "z_order" in presentation.structure_hints
    assert "spatial_sections" in poster.structure_hints


def test_auto_profile_decision_requires_confidence_and_evidence():
    with pytest.raises(ValidationError):
        ProfileDecision(
            selected_profile=ContentProfile.GENERIC,
            source=ProfileSource.AUTO,
            confidence=None,
            evidence=[],
        )

    decision = resolve_profile(
        auto_suggestion=ContentProfile.REVIEW_ARTICLE,
        confidence=0.83,
        evidence=["review title", "narrative synthesis"],
    )
    assert decision.selected_profile is ContentProfile.REVIEW_ARTICLE
    assert decision.source is ProfileSource.AUTO
    assert decision.auto_suggestion is ContentProfile.REVIEW_ARTICLE


def test_user_override_preserves_the_automatic_suggestion():
    decision = resolve_profile(
        auto_suggestion=ContentProfile.RESEARCH_ARTICLE,
        confidence=0.71,
        evidence=["numbered figures"],
        user_override=ContentProfile.POSTER,
    )

    assert decision.selected_profile is ContentProfile.POSTER
    assert decision.source is ProfileSource.USER_OVERRIDE
    assert decision.auto_suggestion is ContentProfile.RESEARCH_ARTICLE
    assert decision.confidence == 0.71
    assert decision.evidence == ["numbered figures"]
