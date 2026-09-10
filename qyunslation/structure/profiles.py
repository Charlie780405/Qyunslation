"""Content-profile priors that are deliberately independent of file formats."""

from __future__ import annotations

from enum import Enum

from pydantic import ConfigDict, Field, model_validator

from .models import ContentProfile, ContractModel, LayoutMode, ProfileSource


class ReadingStrategy(str, Enum):
    READING_ORDER = "READING_ORDER"
    SPATIAL = "SPATIAL"
    HYBRID = "HYBRID"


class ProfileSpec(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content_profile: ContentProfile
    label: str = Field(min_length=1)
    reading_strategy: ReadingStrategy
    expected_layout_modes: tuple[LayoutMode, ...]
    structure_hints: tuple[str, ...]
    has_figure_table_semantics: bool


class ProfileDecision(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_profile: ContentProfile
    source: ProfileSource
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    auto_suggestion: ContentProfile | None = None

    @model_validator(mode="after")
    def validate_provenance(self) -> ProfileDecision:
        if self.source is ProfileSource.AUTO:
            if self.confidence is None or not self.evidence:
                raise ValueError("PROFILE_EVIDENCE_REQUIRED")
            if self.auto_suggestion is not self.selected_profile:
                raise ValueError("PROFILE_AUTO_SUGGESTION_MISMATCH")
        elif self.auto_suggestion is None:
            raise ValueError("PROFILE_AUTO_SUGGESTION_REQUIRED")
        return self


_FLOW_LAYOUTS = (
    LayoutMode.SINGLE,
    LayoutMode.DOUBLE,
    LayoutMode.MULTI,
    LayoutMode.MIXED,
)

_PROFILES = (
    ProfileSpec(
        content_profile=ContentProfile.RESEARCH_ARTICLE,
        label="研究文献",
        reading_strategy=ReadingStrategy.READING_ORDER,
        expected_layout_modes=_FLOW_LAYOUTS,
        structure_hints=(
            "numbered_figures",
            "numbered_tables",
            "captions",
            "references",
        ),
        has_figure_table_semantics=True,
    ),
    ProfileSpec(
        content_profile=ContentProfile.REVIEW_ARTICLE,
        label="综述",
        reading_strategy=ReadingStrategy.READING_ORDER,
        expected_layout_modes=_FLOW_LAYOUTS,
        structure_hints=(
            "narrative_synthesis",
            "numbered_figures",
            "numbered_tables",
            "references",
        ),
        has_figure_table_semantics=True,
    ),
    ProfileSpec(
        content_profile=ContentProfile.PRESENTATION,
        label="演示文稿",
        reading_strategy=ReadingStrategy.SPATIAL,
        expected_layout_modes=(LayoutMode.FREEFORM,),
        structure_hints=(
            "z_order",
            "slide_title",
            "grouped_shapes",
            "speaker_notes",
        ),
        has_figure_table_semantics=False,
    ),
    ProfileSpec(
        content_profile=ContentProfile.POSTER,
        label="Poster",
        reading_strategy=ReadingStrategy.SPATIAL,
        expected_layout_modes=(LayoutMode.FREEFORM, LayoutMode.MULTI),
        structure_hints=(
            "spatial_sections",
            "visual_hierarchy",
            "large_canvas",
            "captions",
        ),
        has_figure_table_semantics=True,
    ),
    ProfileSpec(
        content_profile=ContentProfile.REGULATORY,
        label="法规与申报资料",
        reading_strategy=ReadingStrategy.READING_ORDER,
        expected_layout_modes=_FLOW_LAYOUTS,
        structure_hints=(
            "numbered_sections",
            "controlled_terms",
            "forms",
            "tables",
        ),
        has_figure_table_semantics=True,
    ),
    ProfileSpec(
        content_profile=ContentProfile.LETTER,
        label="书信",
        reading_strategy=ReadingStrategy.READING_ORDER,
        expected_layout_modes=(LayoutMode.SINGLE,),
        structure_hints=("salutation", "body", "closing", "signature"),
        has_figure_table_semantics=False,
    ),
    ProfileSpec(
        content_profile=ContentProfile.GENERIC,
        label="通用文档",
        reading_strategy=ReadingStrategy.HYBRID,
        expected_layout_modes=(*_FLOW_LAYOUTS, LayoutMode.FREEFORM),
        structure_hints=("headings", "paragraphs", "tables", "images"),
        has_figure_table_semantics=False,
    ),
)

_BY_PROFILE = {spec.content_profile: spec for spec in _PROFILES}
if set(_BY_PROFILE) != set(ContentProfile) or len(_BY_PROFILE) != len(_PROFILES):
    raise RuntimeError("content profile registry must cover each ContentProfile once")


def all_content_profiles() -> tuple[ProfileSpec, ...]:
    """Return the immutable content-profile registry."""

    return _PROFILES


def profile_for(content_profile: ContentProfile) -> ProfileSpec:
    """Return structural priors without consulting the source format."""

    return _BY_PROFILE[content_profile]


def suggest_content_profile(
    *,
    figure_caption_count: int = 0,
    table_caption_count: int = 0,
) -> tuple[ContentProfile, float, list[str]]:
    """030j D5：按语义对象推断 profile，与容器格式解耦。"""
    evidence: list[str] = []
    if figure_caption_count:
        evidence.append(f"figure_captions:{figure_caption_count}")
    if table_caption_count:
        evidence.append(f"table_captions:{table_caption_count}")
    if figure_caption_count or table_caption_count:
        confidence = 0.92 if figure_caption_count and table_caption_count else 0.75
        return ContentProfile.RESEARCH_ARTICLE, confidence, evidence
    return ContentProfile.GENERIC, 0.4, evidence or ["no_numbered_semantics"]


def resolve_profile(
    *,
    auto_suggestion: ContentProfile,
    confidence: float,
    evidence: list[str],
    user_override: ContentProfile | None = None,
) -> ProfileDecision:
    """Resolve an explicit decision while retaining automatic evidence."""

    return ProfileDecision(
        selected_profile=user_override or auto_suggestion,
        source=(
            ProfileSource.USER_OVERRIDE if user_override else ProfileSource.AUTO
        ),
        confidence=confidence,
        evidence=evidence,
        auto_suggestion=auto_suggestion,
    )
