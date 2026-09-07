from __future__ import annotations

from qyunslation.structure.capabilities import RuntimeFeature, RuntimeState
from qyunslation.structure.models import ProcessingMode, SourceFormat
from qyunslation.structure.runtime import (
    FeatureProbe,
    RuntimeCapabilitySnapshot,
    decide_runtime_capability,
    probe_runtime_capabilities,
)


def _snapshot(*available: RuntimeFeature) -> RuntimeCapabilitySnapshot:
    enabled = set(available)
    return RuntimeCapabilitySnapshot(
        probes=[
            FeatureProbe(
                feature=feature,
                available=feature in enabled,
                detail="test",
            )
            for feature in RuntimeFeature
        ]
    )


def test_runtime_probe_reports_every_registered_feature():
    snapshot = probe_runtime_capabilities(
        module_available=lambda name: name in {"PIL", "pymupdf", "docx", "pptx", "rapidocr", "onnxruntime"},
        command_finder=lambda name: "/usr/bin/fake" if name == "fc-match" else None,
        environment={},
    )

    assert {item.feature for item in snapshot.probes} == set(RuntimeFeature)
    assert snapshot.for_feature(RuntimeFeature.PDF_ENGINE).available is True
    assert snapshot.for_feature(RuntimeFeature.OFFICE_CONVERTER).available is False
    assert snapshot.for_feature(RuntimeFeature.FONT_PACK).available is True


def test_pdf_native_mode_is_available_when_its_features_exist():
    snapshot = _snapshot(RuntimeFeature.PDF_ENGINE, RuntimeFeature.FONT_PACK)

    decision = decide_runtime_capability(
        SourceFormat.PDF,
        requested_mode=ProcessingMode.NATIVE,
        snapshot=snapshot,
    )

    assert decision.runtime_state is RuntimeState.AVAILABLE
    assert decision.selected_mode is ProcessingMode.NATIVE
    assert decision.missing_features == []


def test_requested_hybrid_mode_does_not_silently_fall_back_to_native():
    snapshot = _snapshot(RuntimeFeature.PDF_ENGINE, RuntimeFeature.FONT_PACK)

    decision = decide_runtime_capability(
        SourceFormat.PDF,
        requested_mode=ProcessingMode.HYBRID,
        snapshot=snapshot,
    )

    assert decision.runtime_state is RuntimeState.UNAVAILABLE
    assert decision.selected_mode is None
    assert set(decision.missing_features) == {
        RuntimeFeature.IMAGE_DECODER,
        RuntimeFeature.OCR_ENGINE,
    }
    assert decision.reason_code == "RUNTIME_FEATURES_MISSING"


def test_legacy_office_requires_converter_before_translation():
    snapshot = _snapshot(RuntimeFeature.OOXML_ENGINE, RuntimeFeature.FONT_PACK)

    for source_format in (SourceFormat.DOC, SourceFormat.PPT):
        decision = decide_runtime_capability(source_format, snapshot=snapshot)
        assert decision.runtime_state is RuntimeState.UNAVAILABLE
        assert decision.selected_mode is None
        assert RuntimeFeature.OFFICE_CONVERTER in decision.missing_features


def test_pptx_native_does_not_require_slide_renderer():
    snapshot = _snapshot(RuntimeFeature.OOXML_ENGINE, RuntimeFeature.FONT_PACK)

    decision = decide_runtime_capability(
        SourceFormat.PPTX,
        requested_mode=ProcessingMode.NATIVE,
        snapshot=snapshot,
    )

    assert decision.runtime_state is RuntimeState.AVAILABLE
    assert decision.selected_mode is ProcessingMode.NATIVE


def test_pptx_rendered_requires_slide_renderer_and_image_stack():
    snapshot = _snapshot(RuntimeFeature.OOXML_ENGINE, RuntimeFeature.FONT_PACK)

    decision = decide_runtime_capability(
        SourceFormat.PPTX,
        requested_mode=ProcessingMode.RENDERED,
        snapshot=snapshot,
    )

    assert decision.runtime_state is RuntimeState.UNAVAILABLE
    assert decision.selected_mode is None
    assert RuntimeFeature.SLIDE_RENDERER in decision.missing_features
    assert RuntimeFeature.IMAGE_DECODER in decision.missing_features
    assert RuntimeFeature.OCR_ENGINE in decision.missing_features


def test_snapshot_rejects_duplicate_or_missing_features():
    probes = [
        FeatureProbe(feature=feature, available=True, detail="test")
        for feature in RuntimeFeature
    ]

    duplicate = [*probes, probes[0]]
    try:
        RuntimeCapabilitySnapshot(probes=duplicate)
    except ValueError as exc:
        assert "RUNTIME_FEATURE_DUPLICATE" in str(exc)
    else:
        raise AssertionError("duplicate feature must fail")

    try:
        RuntimeCapabilitySnapshot(probes=probes[:-1])
    except ValueError as exc:
        assert "RUNTIME_FEATURE_INCOMPLETE" in str(exc)
    else:
        raise AssertionError("missing feature must fail")
