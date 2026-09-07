import pytest
from pydantic import ValidationError

from qyunslation.structure import OutputEditability, ProcessingMode, SourceFormat
from qyunslation.structure.capabilities import (
    CapabilityDecision,
    RequirementLevel,
    RuntimeFeature,
    RuntimeState,
    all_format_capabilities,
    capability_for,
    source_format_for_extension,
    source_formats_for_mime,
)


CORE_FORMATS = {
    SourceFormat.PDF,
    SourceFormat.DOCX,
    SourceFormat.PNG,
    SourceFormat.JPEG,
    SourceFormat.WEBP,
    SourceFormat.BMP,
    SourceFormat.TIFF,
    SourceFormat.PPTX,
}
NORMALIZE_FORMATS = {SourceFormat.DOC, SourceFormat.PPT}
CONDITIONAL_FORMATS = {
    SourceFormat.SVG,
    SourceFormat.GIF,
    SourceFormat.HEIF,
    SourceFormat.HEIC,
    SourceFormat.AVIF,
}


def test_registry_has_one_policy_for_every_known_source_format():
    capabilities = all_format_capabilities()

    assert {item.source_format for item in capabilities} == set(SourceFormat)
    assert len(capabilities) == len(SourceFormat)


def test_plan030_format_requirement_levels_are_exact():
    by_level = {
        level: {
            item.source_format
            for item in all_format_capabilities()
            if item.requirement_level is level
        }
        for level in RequirementLevel
    }

    assert by_level[RequirementLevel.CORE] == CORE_FORMATS
    assert by_level[RequirementLevel.NORMALIZE] == NORMALIZE_FORMATS
    assert by_level[RequirementLevel.CONDITIONAL] == CONDITIONAL_FORMATS
    assert by_level[RequirementLevel.UNSUPPORTED] == {SourceFormat.UNKNOWN}


def test_legacy_office_formats_have_explicit_normalization_targets():
    assert capability_for(SourceFormat.DOC).normalizes_to is SourceFormat.DOCX
    assert capability_for(SourceFormat.PPT).normalizes_to is SourceFormat.PPTX


def test_extension_lookup_is_case_insensitive_and_never_falls_back_to_text():
    assert source_format_for_extension("paper.PDF") is SourceFormat.PDF
    assert source_format_for_extension("photo.jpeg") is SourceFormat.JPEG
    assert source_format_for_extension("scan.TIF") is SourceFormat.TIFF
    assert source_format_for_extension("deck.ppt") is SourceFormat.PPT
    assert source_format_for_extension("payload.unknown") is SourceFormat.UNKNOWN
    assert source_format_for_extension("no-extension") is SourceFormat.UNKNOWN


def test_mime_lookup_can_express_ambiguous_or_unknown_results():
    assert source_formats_for_mime("image/jpeg") == (SourceFormat.JPEG,)
    assert source_formats_for_mime("application/pdf") == (SourceFormat.PDF,)
    assert source_formats_for_mime("application/octet-stream") == (
        SourceFormat.UNKNOWN,
    )


def test_extensions_are_owned_by_only_one_format():
    owners: dict[str, SourceFormat] = {}
    for capability in all_format_capabilities():
        for extension in capability.extensions:
            assert extension.startswith(".")
            assert extension == extension.lower()
            assert extension not in owners, (
                f"{extension} is owned by both {owners[extension]} "
                f"and {capability.source_format}"
            )
            owners[extension] = capability.source_format


def test_pptx_declares_native_and_rendered_outputs_without_hiding_editability():
    pptx = capability_for(SourceFormat.PPTX)
    modes = {item.mode: item for item in pptx.modes}

    assert modes[ProcessingMode.NATIVE].output_editability is OutputEditability.EDITABLE
    assert modes[ProcessingMode.RENDERED].output_editability is OutputEditability.RASTERIZED
    assert {"PPTX", "PDF", "IMAGE_SET"}.issubset(
        set(modes[ProcessingMode.RENDERED].output_formats)
    )
    assert RuntimeFeature.SLIDE_RENDERER in modes[ProcessingMode.RENDERED].required_features


def test_conditional_format_policy_does_not_claim_runtime_availability():
    svg = capability_for(SourceFormat.SVG)

    unavailable = CapabilityDecision(
        source_format=svg.source_format,
        requirement_level=svg.requirement_level,
        runtime_state=RuntimeState.UNAVAILABLE,
        requested_mode=ProcessingMode.RENDERED,
        selected_mode=None,
        missing_features=[RuntimeFeature.SVG_DECODER],
        reason_code="RUNTIME_FEATURE_MISSING",
    )
    available = unavailable.model_copy(
        update={
            "runtime_state": RuntimeState.AVAILABLE,
            "selected_mode": ProcessingMode.RENDERED,
            "missing_features": [],
            "reason_code": None,
        }
    )

    assert unavailable.requirement_level is RequirementLevel.CONDITIONAL
    assert available.requirement_level is RequirementLevel.CONDITIONAL
    assert unavailable.runtime_state is RuntimeState.UNAVAILABLE
    assert available.runtime_state is RuntimeState.AVAILABLE


def test_unavailable_or_degraded_decisions_require_a_reason():
    with pytest.raises(ValidationError):
        CapabilityDecision(
            source_format=SourceFormat.PDF,
            requirement_level=RequirementLevel.CORE,
            runtime_state=RuntimeState.UNAVAILABLE,
            requested_mode=ProcessingMode.NATIVE,
            selected_mode=None,
            missing_features=[RuntimeFeature.PDF_ENGINE],
        )


def test_runtime_decision_rejects_contradictory_availability_state():
    with pytest.raises(ValidationError) as available_error:
        CapabilityDecision(
            source_format=SourceFormat.PDF,
            requirement_level=RequirementLevel.CORE,
            runtime_state=RuntimeState.AVAILABLE,
            requested_mode=ProcessingMode.NATIVE,
            selected_mode=ProcessingMode.NATIVE,
            missing_features=[RuntimeFeature.PDF_ENGINE],
        )
    assert "CAPABILITY_AVAILABLE_HAS_MISSING_FEATURES" in str(available_error.value)

    with pytest.raises(ValidationError) as unavailable_error:
        CapabilityDecision(
            source_format=SourceFormat.PDF,
            requirement_level=RequirementLevel.CORE,
            runtime_state=RuntimeState.UNAVAILABLE,
            requested_mode=ProcessingMode.NATIVE,
            selected_mode=ProcessingMode.NATIVE,
            missing_features=[RuntimeFeature.PDF_ENGINE],
            reason_code="RUNTIME_FEATURE_MISSING",
        )
    assert "CAPABILITY_UNAVAILABLE_HAS_MODE" in str(unavailable_error.value)


def test_runtime_decision_must_match_registered_policy_and_modes():
    with pytest.raises(ValidationError) as level_error:
        CapabilityDecision(
            source_format=SourceFormat.PDF,
            requirement_level=RequirementLevel.CONDITIONAL,
            runtime_state=RuntimeState.UNKNOWN,
        )
    assert "CAPABILITY_REQUIREMENT_MISMATCH" in str(level_error.value)

    with pytest.raises(ValidationError) as mode_error:
        CapabilityDecision(
            source_format=SourceFormat.DOCX,
            requirement_level=RequirementLevel.CORE,
            runtime_state=RuntimeState.AVAILABLE,
            requested_mode=ProcessingMode.RENDERED,
            selected_mode=ProcessingMode.RENDERED,
        )
    assert "CAPABILITY_MODE_UNSUPPORTED" in str(mode_error.value)


def test_unknown_format_is_an_explicit_fail_fast_capability():
    unknown = capability_for(SourceFormat.UNKNOWN)

    assert unknown.requirement_level is RequirementLevel.UNSUPPORTED
    assert unknown.modes == ()
    assert unknown.issue_code == "UNSUPPORTED_FORMAT"
